"""Classifier refusal rate by depth level for the depth vs harm pilot.

Usage:
    python analyze_refusals.py main_results/responses.csv
    python analyze_refusals.py main_results/responses.csv --dev T21,T22,T23,T24,T25
    python analyze_refusals.py main_results/responses.csv --dev T21,T22,T23,T24,T25 --workbook PROMPTS.xlsx

--dev lists the topic IDs of the development set. Without it, topics whose
ID starts with P are treated as the development set.

Reads responses.csv from run_prompts.py and prints:
  1. Refusal counts and rates by level, with 95% Wilson confidence intervals,
     for all 75 prompts, the 60 main prompts and the 15 development prompts
  2. The same by run, to show run-to-run consistency
  3. Prompt-level consistency: how many prompts got the same outcome every run
  4. Per-topic patterns (refusals at L1/L2/L3 out of the number of runs)
  5. Trend tests:
       - Cochran-Armitage trend test on all responses (treats responses as
         independent, so its p-value is optimistic)
       - Within-topic permutation test (primary): level labels are shuffled
         within each topic, keeping each prompt's runs together, so topic and
         repeated runs are respected. Exact-enough with 100,000 shuffles.
  6. Classifier categories
  7. Optional exploratory checks on the depth confound (descriptive only):
       - prompt length (input_tokens) for refused vs answered prompts, by level
       - with --workbook: blind depth ratings by level (depth check), and for
         refused vs answered prompts within each level. Needs openpyxl and
         the workbook saved in Excel so the rating formulas have values.

A refusal is stop_reason == "refusal". item_id is expected as TOPIC-LEVEL,
for example T01-L2. Topics starting with P are the development set.

Needs only Python itself (plus openpyxl for --workbook). Results are also saved to refusal_summary.csv
next to the input file.
"""

import argparse
import csv
import math
import os
import random
import sys
from collections import Counter, defaultdict

SEED = 20261104
N_PERM = 100_000
LEVELS = ["L1", "L2", "L3"]


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def cochran_armitage(counts):
    """counts: list of (refused, total) for scores 1, 2, 3. Returns (z, two-sided p)."""
    scores = [1, 2, 3]
    N = sum(n for _, n in counts)
    R = sum(k for k, _ in counts)
    if N == 0 or R in (0, N):
        return float("nan"), float("nan")
    p = R / N
    t = sum(s * (k - n * p) for s, (k, n) in zip(scores, counts))
    var = p * (1 - p) * (sum(n * s * s for s, (_, n) in zip(scores, counts))
                         - sum(n * s for s, (_, n) in zip(scores, counts)) ** 2 / N)
    z = t / math.sqrt(var)
    return z, math.erfc(abs(z) / math.sqrt(2))


def permutation_test(prompt_rate):
    """prompt_rate: {topic: {level: refusal proportion across runs}}.
    Statistic: sum over topics of sum(level score * proportion).
    Shuffles level labels within each topic. Returns (observed, one-sided p, two-sided p)."""
    topics = [[prompt_rate[t][L] for L in LEVELS] for t in sorted(prompt_rate)
              if all(L in prompt_rate[t] for L in LEVELS)]
    if not topics:
        return float("nan"), float("nan"), float("nan")
    scores = [1, 2, 3]
    obs = sum(sum(s * v for s, v in zip(scores, vals)) for vals in topics)
    # centre so two-sided compares distance from the null mean
    null_mean = sum(2 * sum(vals) for vals in topics)
    rng = random.Random(SEED)
    ge = absge = 0
    for _ in range(N_PERM):
        stat = 0.0
        for vals in topics:
            v = vals[:]
            rng.shuffle(v)
            stat += v[0] + 2 * v[1] + 3 * v[2]
        if stat >= obs - 1e-12:
            ge += 1
        if abs(stat - null_mean) >= abs(obs - null_mean) - 1e-12:
            absge += 1
    return obs, (ge + 1) / (N_PERM + 1), (absge + 1) / (N_PERM + 1)


def load_depth(path, sheet="Items"):
    """Return {item_id: blind depth rating} from the Items sheet."""
    import openpyxl
    ws = openpyxl.load_workbook(path, data_only=True)[sheet]
    header = [str(c.value).strip().lower() if c.value is not None else "" for c in ws[1]]
    try:
        id_col = header.index("item_id")
        depth_col = next(i for i, h in enumerate(header) if h.startswith("depth"))
    except (ValueError, StopIteration):
        sys.exit(f"Sheet '{sheet}' needs an item_id column and a depth column.")
    depth = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        item, d = row[id_col], row[depth_col]
        try:
            depth[str(item).strip()] = float(d)
        except (TypeError, ValueError):
            continue
    return depth


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return float("nan")
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def fmt_rate(k, n):
    lo, hi = wilson(k, n)
    pct = 100 * k / n if n else float("nan")
    return f"{k:3d} of {n:3d}  {pct:5.1f}%  (95% CI {100*lo:5.1f}-{100*hi:5.1f}%)"


def main():
    ap = argparse.ArgumentParser(description="Classifier refusal rate by depth level.")
    ap.add_argument("responses", help="path to responses.csv")
    ap.add_argument("--dev", default="", help="comma-separated development topic IDs, e.g. T21,T22")
    ap.add_argument("--workbook", help="optional: workbook with blind depth ratings on the Items sheet")
    args = ap.parse_args()
    path = args.responses
    dev_ids = {t.strip().upper() for t in args.dev.split(",") if t.strip()}
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        topic, _, level = r["item_id"].rpartition("-")
        r["topic"], r["level"] = topic, level
        r["refused"] = r["stop_reason"] == "refusal"
        r["dev"] = topic.upper() in dev_ids if dev_ids else topic.upper().startswith("P")
    bad = [r["item_id"] for r in rows if r["level"] not in LEVELS]
    if bad:
        sys.exit(f"Unexpected item_id format, for example {bad[0]}. Expected TOPIC-L1/L2/L3.")
    runs = sorted({int(r["run"]) for r in rows})
    if dev_ids:
        missing = dev_ids - {r["topic"].upper() for r in rows}
        if missing:
            sys.exit(f"--dev topic IDs not found in the data: {', '.join(sorted(missing))}")
    if not any(r["dev"] for r in rows):
        print("\nNote: no development topics found, so 'Main prompts' equals all prompts. "
              "Pass --dev with the development topic IDs.")
    summary = []

    subsets = [("All prompts", rows),
               ("Main prompts (non-development)", [r for r in rows if not r["dev"]]),
               ("Development prompts", [r for r in rows if r["dev"]])]

    print(f"\n{len(rows)} responses, {len({r['item_id'] for r in rows})} prompts, "
          f"{len({r['topic'] for r in rows})} topics, runs {runs}")
    other = Counter(r["stop_reason"] for r in rows if not r["refused"])
    print(f"Not refused by the classifier: {dict(other)}")

    print("\n1. CLASSIFIER REFUSALS BY LEVEL (all runs)")
    for name, sub in subsets:
        if not sub:
            continue
        nprompts = len({r["item_id"] for r in sub})
        print(f"\n  {name}: {nprompts} prompts")
        for L in LEVELS:
            s = [r for r in sub if r["level"] == L]
            k = sum(r["refused"] for r in s)
            print(f"    {L}  {fmt_rate(k, len(s))}")
            lo, hi = wilson(k, len(s))
            summary.append({"subset": name, "run": "all", "level": L, "refused": k,
                            "total": len(s), "rate": round(k / len(s), 4) if s else "",
                            "ci_low": round(lo, 4), "ci_high": round(hi, 4)})
        k = sum(r["refused"] for r in sub)
        print(f"    All {fmt_rate(k, len(sub))}")

    print("\n2. BY RUN (all prompts)")
    for run in runs:
        s = [r for r in rows if int(r["run"]) == run]
        parts = []
        for L in LEVELS:
            sl = [r for r in s if r["level"] == L]
            k = sum(r["refused"] for r in sl)
            parts.append(f"{L} {k}/{len(sl)}")
            lo, hi = wilson(k, len(sl))
            summary.append({"subset": "All prompts", "run": run, "level": L, "refused": k,
                            "total": len(sl), "rate": round(k / len(sl), 4) if sl else "",
                            "ci_low": round(lo, 4), "ci_high": round(hi, 4)})
        print(f"  Run {run}:  " + "   ".join(parts))

    by_prompt = defaultdict(list)
    for r in rows:
        by_prompt[r["item_id"]].append(r["refused"])
    if len(runs) > 1:
        print("\n3. PROMPT-LEVEL CONSISTENCY ACROSS RUNS")
        for L in LEVELS:
            ps = {i: v for i, v in by_prompt.items() if i.endswith(L)}
            always = sum(all(v) for v in ps.values())
            never = sum(not any(v) for v in ps.values())
            mixed = len(ps) - always - never
            print(f"  {L}: refused every run {always}, never refused {never}, mixed {mixed}  (of {len(ps)})")
        same = sum(all(v) or not any(v) for v in by_prompt.values())
        print(f"  Same outcome on every run: {same} of {len(by_prompt)} prompts")

    print("\n4. PER-TOPIC REFUSALS (L1 / L2 / L3, out of runs per prompt)")
    prompt_rate = defaultdict(dict)
    topic_counts = defaultdict(dict)
    for item, v in by_prompt.items():
        topic, _, L = item.rpartition("-")
        prompt_rate[topic][L] = sum(v) / len(v)
        topic_counts[topic][L] = f"{sum(v)}/{len(v)}"
    mono = l3_gt_l1 = 0
    for t in sorted(topic_counts):
        c = topic_counts[t]
        pr = prompt_rate[t]
        if all(L in pr for L in LEVELS):
            mono += pr["L1"] <= pr["L2"] <= pr["L3"]
            l3_gt_l1 += pr["L3"] > pr["L1"]
        print(f"  {t}:  " + "   ".join(c.get(L, "-") for L in LEVELS))
    print(f"  Topics never decreasing L1->L2->L3: {mono} of {len(topic_counts)}")
    print(f"  Topics with more L3 than L1 refusals: {l3_gt_l1} of {len(topic_counts)}")

    print("\n5. TREND TESTS")
    for name, sub in subsets:
        if not sub:
            continue
        counts = [(sum(r["refused"] for r in sub if r["level"] == L),
                   sum(1 for r in sub if r["level"] == L)) for L in LEVELS]
        z, p = cochran_armitage(counts)
        topics = {r["topic"] for r in sub}
        _, p1, p2 = permutation_test({t: prompt_rate[t] for t in topics})
        print(f"\n  {name}")
        print(f"    Within-topic permutation test (primary): one-sided p = {p1:.2g}, two-sided p = {p2:.2g}")
        print(f"    Cochran-Armitage on responses (ignores clustering): z = {z:.2f}, p = {p:.2g}")
    print(f"\n  Permutation tests use {N_PERM:,} shuffles; the smallest possible p is {1/(N_PERM+1):.1g}.")

    print("\n6. CLASSIFIER CATEGORIES (refusals only)")
    cats = Counter(r["refusal_category"] or "(none)" for r in rows if r["refused"])
    for cat, n in cats.most_common():
        print(f"  {cat}: {n}")

    print("\n7. OPTIONAL EXPLORATORY CHECKS (depth confound, descriptive only)")
    print("  A prompt counts as refused if the classifier refused it on most runs.")
    tokens = {}
    for r in rows:
        try:
            tokens.setdefault(r["item_id"], int(r["input_tokens"]))
        except (KeyError, ValueError):
            pass
    refused_prompt = {i: sum(v) > len(v) / 2 for i, v in by_prompt.items()}

    print("\n  Prompt length (input tokens), refused vs answered prompts:")
    for L in LEVELS:
        ref = [tokens[i] for i in by_prompt if i.endswith(L) and i in tokens and refused_prompt[i]]
        ans = [tokens[i] for i in by_prompt if i.endswith(L) and i in tokens and not refused_prompt[i]]
        print(f"    {L}  refused n={len(ref):2d} mean {mean(ref):6.1f} median {median(ref):6.1f}"
              f"   |   answered n={len(ans):2d} mean {mean(ans):6.1f} median {median(ans):6.1f}")

    if args.workbook:
        depth = load_depth(args.workbook)
        missing = [i for i in by_prompt if i not in depth]
        if missing:
            print(f"\n  No depth rating found for {len(missing)} prompts, for example {missing[0]}. They are left out.")
        print("\n  Depth check: blind depth rating (1-5) by level")
        for L in LEVELS:
            ds = [depth[i] for i in by_prompt if i.endswith(L) and i in depth]
            print(f"    {L}  n={len(ds):2d} mean {mean(ds):.2f}  median {median(ds):.1f}")
        tops = defaultdict(dict)
        for i, d in depth.items():
            t, _, L = i.rpartition("-")
            if i in by_prompt:
                tops[t][L] = d
        full = [t for t in tops if "L1" in tops[t] and "L3" in tops[t]]
        print(f"    Topics with L3 rated deeper than L1: {sum(tops[t]['L3'] > tops[t]['L1'] for t in full)} of {len(full)}")
        print("\n  Blind depth rating, refused vs answered prompts:")
        for L in LEVELS:
            ref = [depth[i] for i in by_prompt if i.endswith(L) and i in depth and refused_prompt[i]]
            ans = [depth[i] for i in by_prompt if i.endswith(L) and i in depth and not refused_prompt[i]]
            print(f"    {L}  refused n={len(ref):2d} mean {mean(ref):.2f}   |   answered n={len(ans):2d} mean {mean(ans):.2f}")
    else:
        print("\n  Add --workbook PROMPTS.xlsx to include the blind depth ratings.")
    print("\n  With so few prompts per group, read these as patterns, not tests.")

    out = os.path.join(os.path.dirname(os.path.abspath(path)), "refusal_summary.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)
    print(f"\nSaved the rate table to {out}\n")


if __name__ == "__main__":
    main()
