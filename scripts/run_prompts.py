"""Run the depth vs harm pilot prompts through the Claude API.

Reads prompts from the Items sheet of a pilot workbook, sends each one as a
fresh single-turn request (no system prompt, no conversation history), and
saves every response, refusals included, to CSV.

Setup:
    pip install anthropic openpyxl
    export ANTHROPIC_API_KEY=...        # from console.anthropic.com

Usage:
    # check the job list without calling the API
    python run_prompts.py depth_vs_harm_practice_workbook.xlsx --runs 1 --dry-run

    # practice run: 15 prompts, 1 run each
    python run_prompts.py depth_vs_harm_practice_workbook.xlsx --runs 1 --out practice

    # main run: 60 prompts x 3 runs
    python run_prompts.py depth_vs_harm_pilot_workbook.xlsx --runs 3 --out main

Outputs (in the --out folder):
    responses.csv        every response with item_id, run, model, timestamp,
                         stop reason and token counts (unblinded, for analysis)
    responses_blind.csv  shuffled responses with only a code_id and the text,
                         for blind coding
    blind_key.csv        code_id -> response_id mapping (don't open while coding)

Staged runs: you can run --runs 1 first, code those, then rerun the same
command with --runs 3 and the same --out folder. Only runs 2 and 3 are sent,
and they're blinded separately in responses_blind_batch2.csv with new code
IDs, so the codes you already entered stay valid.

The run is resumable: if it stops partway, rerun the same command and it
skips responses already saved in responses.csv.

Notes on the study conditions:
    - No system prompt, and no temperature parameter (this model doesn't
      accept sampling parameters, so the API default always applies).
    - Thinking can't be turned off on this model. Effort is set explicitly
      (default "medium", the API default) so it's recorded, not implied.
    - Server-side refusal fallbacks are deliberately NOT enabled. A fallback
      would answer a refused prompt with a different model, which would hide
      exactly the refusals this study measures.
    - stop_reason "refusal" means the API's safety classifier declined the
      request before or during generation. A refusal written by the model
      itself comes back as ordinary text with stop_reason "end_turn". Both
      are saved, so you can report them separately.
"""

import argparse
import csv
import os
import random
import sys
from datetime import datetime, timezone

import anthropic
import openpyxl

FIELDS = [
    "response_id", "item_id", "model", "run", "timestamp", "response_text",
    "stop_reason", "refusal_category", "refusal_explanation",
    "effort", "input_tokens", "output_tokens", "request_id", "run_order",
]


def load_items(path, sheet):
    """Return [(item_id, prompt_text)] for rows with a prompt and Include != No."""
    ws = openpyxl.load_workbook(path, data_only=True)[sheet]
    header = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]
    col = {name: i for i, name in enumerate(header)}
    for needed in ("item_id", "prompt_text"):
        if needed not in col:
            sys.exit(f"Sheet '{sheet}' has no '{needed}' column.")
    items = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        item_id, prompt = row[col["item_id"]], row[col["prompt_text"]]
        include = row[col["include"]] if "include" in col else None
        if not item_id or not prompt or not str(prompt).strip():
            continue
        if include is not None and str(include).strip().lower() == "no":
            continue
        items.append((str(item_id).strip(), str(prompt).strip()))
    return items


def already_done(path):
    if not os.path.exists(path):
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {row["response_id"] for row in csv.DictReader(f)}


def run_one(client, model, effort, prompt):
    response = client.messages.create(
        model=model,
        max_tokens=16000,
        output_config={"effort": effort},
        messages=[{"role": "user", "content": prompt}],
    )
    text = "\n".join(b.text for b in response.content if b.type == "text")
    category = explanation = ""
    if response.stop_reason == "refusal" and response.stop_details:
        category = response.stop_details.category or ""
        explanation = response.stop_details.explanation or ""
    return {
        "model": response.model,
        "response_text": text,
        "stop_reason": response.stop_reason,
        "refusal_category": category,
        "refusal_explanation": explanation,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "request_id": getattr(response, "_request_id", "") or "",
    }


def write_blind(out_dir, seed):
    """Blind the responses not yet in blind_key.csv.

    The first batch goes to responses_blind.csv. A later batch (for example
    runs 2 and 3 added after run 1 was coded) goes to responses_blind_batch2.csv,
    batch3, and so on, with code IDs continuing from the last batch, so codes
    you've already entered never change. blind_key.csv keeps every batch.
    Returns (file name, number of responses), or (None, 0) if nothing is new.
    """
    with open(os.path.join(out_dir, "responses.csv"), newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    key_path = os.path.join(out_dir, "blind_key.csv")
    keyed, last_code = set(), 0
    if os.path.exists(key_path):
        with open(key_path, newline="", encoding="utf-8") as f:
            for k in csv.DictReader(f):
                keyed.add(k["response_id"])
                last_code = max(last_code, int(k["code_id"][1:]))
    rows = [r for r in rows if r["response_id"] not in keyed]
    if not rows:
        return None, 0
    batch = 1
    if keyed:
        batch = 2
        while os.path.exists(os.path.join(out_dir, f"responses_blind_batch{batch}.csv")):
            batch += 1
    name = "responses_blind.csv" if batch == 1 else f"responses_blind_batch{batch}.csv"
    random.Random(seed + batch).shuffle(rows)
    with open(os.path.join(out_dir, name), "w", newline="", encoding="utf-8") as fb, \
         open(key_path, "a", newline="", encoding="utf-8") as fk:
        blind, key = csv.writer(fb), csv.writer(fk)
        blind.writerow(["code_id", "response_text"])
        if not keyed:
            key.writerow(["code_id", "response_id"])
        for i, row in enumerate(rows, last_code + 1):
            code_id = f"C{i:03d}"
            blind.writerow([code_id, row["response_text"]])
            key.writerow([code_id, row["response_id"]])
    return name, len(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("workbook")
    p.add_argument("--sheet", default="Items")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--model", default="claude-opus-5-5")
    p.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--seed", type=int, default=20261028, help="seed for the run order and blinding shuffle")
    p.add_argument("--out", default="results")
    p.add_argument("--dry-run", action="store_true", help="print the job list without calling the API")
    args = p.parse_args()

    items = load_items(args.workbook, args.sheet)
    if not items:
        sys.exit("No prompts found. Fill in prompt_text on the Items sheet first.")
    jobs = [(item_id, prompt, run) for item_id, prompt in items for run in range(1, args.runs + 1)]
    random.Random(args.seed).shuffle(jobs)
    print(f"{len(items)} prompts x {args.runs} runs = {len(jobs)} requests, model {args.model}, effort {args.effort}")

    if args.dry_run:
        for n, (item_id, _, run) in enumerate(jobs, 1):
            print(f"{n:4d}  {item_id}-R{run}")
        return

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "responses.csv")
    done = already_done(out_path)
    if done:
        print(f"Resuming: {len(done)} responses already saved.")
    new_file = not os.path.exists(out_path)
    client = anthropic.Anthropic(max_retries=5)
    failures = 0

    with open(out_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        for order, (item_id, prompt, run) in enumerate(jobs, 1):
            response_id = f"{item_id}-R{run}"
            if response_id in done:
                continue
            try:
                result = run_one(client, args.model, args.effort, prompt)
            except anthropic.BadRequestError as e:
                sys.exit(f"Request rejected for {response_id}: {e}. Check the model name and settings.")
            except anthropic.AuthenticationError:
                sys.exit("Authentication failed. Set ANTHROPIC_API_KEY.")
            except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError) as e:
                failures += 1
                print(f"  {response_id}: failed after retries ({type(e).__name__}). Rerun to retry it.")
                continue
            writer.writerow({
                "response_id": response_id, "item_id": item_id, "run": run,
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "effort": args.effort, "run_order": order, **result,
            })
            f.flush()
            # progress only: item IDs and outcomes stay hidden until coding is done
            print(f"  [{order}/{len(jobs)}] saved")

    if failures:
        print(f"{failures} requests failed. Rerun the same command to finish them before blinding.")
        return
    name, n = write_blind(args.out, args.seed)
    if name:
        print(f"Done. {n} new responses blinded in {args.out}/{name}")
    else:
        print("Done. No new responses to blind.")


if __name__ == "__main__":
    main()
