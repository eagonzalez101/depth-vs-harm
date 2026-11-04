"""Build a by-topic refusal table for the qualitative review of topics.

Usage:
    python topic_table.py main_results/responses.csv PROMPTS.xlsx --dev T21,T22,T23,T24,T25

Writes topic_refusals.xlsx next to responses.csv, one row per topic, sorted
into three groups by the first level the classifier refused on most runs:
    Refused from L2, Refused at L3 only, Never refused (and From L1 if any).

Columns: group, topic, set (main or development), domain and description
from the Topics sheet, refusals at each level (out of the runs), the blind
depth rating and prompt length at each level, the three prompts, and an
empty notes column for your own review.

Needs openpyxl. Close the workbook in Excel first.
"""

import argparse
import csv
import os
import sys
from collections import defaultdict

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

LEVELS = ["L1", "L2", "L3"]
GROUPS = ["Refused from L1", "Refused from L2", "Refused at L3 only", "Never refused"]


def sheet_rows(wb, name):
    if name not in wb.sheetnames:
        return []
    ws = wb[name]
    header = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]
    return [dict(zip(header, row)) for row in ws.iter_rows(min_row=2, values_only=True)]


def find_key(row, start):
    return next((k for k in row if k.lower().startswith(start)), None)


def main():
    ap = argparse.ArgumentParser(description="By-topic refusal table.")
    ap.add_argument("responses")
    ap.add_argument("workbook")
    ap.add_argument("--dev", default="", help="comma-separated development topic IDs")
    args = ap.parse_args()
    dev = {t.strip().upper() for t in args.dev.split(",") if t.strip()}

    with open(args.responses, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    refused = defaultdict(list)
    tokens = {}
    for r in rows:
        refused[r["item_id"]].append(r["stop_reason"] == "refusal")
        if r.get("input_tokens"):
            tokens.setdefault(r["item_id"], int(r["input_tokens"]))

    wb = openpyxl.load_workbook(args.workbook, data_only=True)
    items = {}
    for row in sheet_rows(wb, "Items"):
        if row.get("item_id"):
            items[str(row["item_id"]).strip()] = row
    topics = {}
    for row in sheet_rows(wb, "Topics"):
        if row.get("topic_id"):
            topics[str(row["topic_id"]).strip()] = row

    by_topic = defaultdict(dict)
    for item in refused:
        t, _, L = item.rpartition("-")
        by_topic[t][L] = item

    table = []
    for t, lv in by_topic.items():
        majority = {L: sum(refused[lv[L]]) > len(refused[lv[L]]) / 2 for L in LEVELS if L in lv}
        first = next((L for L in LEVELS if majority.get(L)), None)
        group = {"L1": GROUPS[0], "L2": GROUPS[1], "L3": GROUPS[2], None: GROUPS[3]}[first]
        trow = topics.get(t, {})
        desc_key = next((k for k in trow if k.lower().startswith("topic") and k.lower() != "topic_id"), None)
        out = {
            "group": group,
            "topic": t,
            "set": "development" if t.upper() in dev else "main",
            "domain": trow.get("domain") or "",
            "description": (trow.get(desc_key) if desc_key else "") or "",
        }
        for L in LEVELS:
            item = lv.get(L)
            v = refused.get(item, [])
            out[f"{L} refused"] = f"{sum(v)}/{len(v)}" if v else ""
        for L in LEVELS:
            irow = items.get(lv.get(L, ""), {})
            dk = find_key(irow, "depth") if irow else None
            out[f"{L} depth"] = irow.get(dk) if dk else ""
        for L in LEVELS:
            out[f"{L} tokens"] = tokens.get(lv.get(L, ""), "")
        for L in LEVELS:
            out[f"{L} prompt"] = items.get(lv.get(L, ""), {}).get("prompt_text") or ""
        out["notes"] = ""
        table.append(out)
    table.sort(key=lambda r: (GROUPS.index(r["group"]), r["topic"]))

    out_wb = openpyxl.Workbook()
    ws = out_wb.active
    ws.title = "By topic"
    cols = list(table[0])
    ws.append(cols)
    for r in table:
        ws.append([r[c] for c in cols])
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.freeze_panes = "C2"
    red = PatternFill("solid", fgColor="F4CCCC")
    pink = PatternFill("solid", fgColor="FCE8E6")
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            name = cols[cell.column - 1]
            if name.endswith("refused") and cell.value:
                k, n = map(int, str(cell.value).split("/"))
                if k and k == n:
                    cell.fill = red
                elif k:
                    cell.fill = pink
            if name.endswith("prompt") or name in ("description", "notes"):
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            else:
                cell.alignment = Alignment(vertical="top")
    widths = {"group": 18, "topic": 8, "set": 12, "domain": 22, "description": 30, "notes": 40}
    for i, name in enumerate(cols, 1):
        w = widths.get(name, 45 if name.endswith("prompt") else 11)
        ws.column_dimensions[get_column_letter(i)].width = w

    summary = out_wb.create_sheet("Group counts")
    summary.append(["group", "topics", "main", "development"])
    for g in GROUPS:
        g_rows = [r for r in table if r["group"] == g]
        if g_rows or g != GROUPS[0]:
            summary.append([g, len(g_rows), sum(r["set"] == "main" for r in g_rows),
                            sum(r["set"] == "development" for r in g_rows)])
    for c in summary[1]:
        c.font = Font(bold=True)

    path = os.path.join(os.path.dirname(os.path.abspath(args.responses)), "topic_refusals.xlsx")
    out_wb.save(path)
    missing = [t for t in by_topic if t not in topics]
    if missing:
        print(f"Note: no Topics row for {', '.join(sorted(missing))}, so domain and description are blank there.")
    print(f"Wrote {path} with {len(table)} topics.")


if __name__ == "__main__":
    main()
