# Does Claude's safety classifier mistake depth for danger?

A pilot study of over-refusal on benign chemical-threat questions · Eduardo, PhD, chemical threat toxicology · November 2026

**Project page:** https://eagonzalez101.github.io/depth-vs-harm/

## Key finding

On chemical-threat questions that a toxicology expert judged to carry no practical uplift, Claude's API safety classifier refused more often as the questions got more technical: **1% at public level, 43% at undergraduate level and 76% at graduate or clinician level.** Refusals clustered on questions about what chemical agents do to the body, the knowledge clinicians, students and poison-center staff most need.

![Classifier refusal rate by depth level](figures/refusal_by_level.png)

## Why it matters

Safety filters are meant to block information that helps cause harm. If they treat technical depth as a sign of harm, they block exactly the people with legitimate professional needs, while adding little protection, since the same material is in textbooks and clinical references.

## What I did

- **75 prompts:** 25 benign chemical-threat topics, each written at three depth levels: public (L1), undergraduate (L2) and graduate or clinician (L3).
- **Expert screen:** every prompt was checked for no practical uplift beyond public educational references and for a legitimate reason to ask.
- **Model:** Claude Opus 5.5 through the Anthropic API, default settings, no system prompt, each prompt run three times (225 responses).
- **Outcome:** whether the API's safety classifier refused the request.

## Results

| Depth level | Classifier refusals |
| --- | --- |
| L1 · Public | 1 of 75 (1%) |
| L2 · Undergraduate | 32 of 75 (43%) |
| L3 · Graduate or clinician | 57 of 75 (76%) |

The trend was highly significant (within-topic permutation test, p < 0.0001), and it held in every subset. No topic was ever refused less at a deeper level.

- **Refusals track expert-rated depth:** the expert also rated every prompt's depth from 1 (news level) to 5 (specialist), blind and before any run. Refusals climbed with that rating, from 0% of responses at rating 1 to 3%, 43%, 73% and 81% at rating 5 (exploratory).
- **Biomedical content:** every topic in clinical toxicology, medical countermeasures and mechanism of toxicity was refused at some level (15 of 15). Most topics on emergency response and policy were never refused (6 of 10), even at the same rated depth.

## How it was controlled

- Depth was rated blind, with topic and level hidden, before any model run.
- Prompts were drafted by a different company's model, so Claude wasn't tested on its own writing.
- Refusal fallbacks were disabled, so no refused prompt was quietly answered by another model.
- Prompts were sent in a randomized order, and three runs showed the classifier was almost deterministic (73 of 75 prompts got the same outcome every time).

## Limitations

- One expert chose topics, screened prompts and rated depth, with no second rater.
- Deeper questions are also more specific, so depth can't be fully separated from specificity and vocabulary.
- Results apply to one model and one classifier at one point in time.

## Full study

| | |
| --- | --- |
| [Methodology](docs/methodology.md) | Design, settings, analysis plan, scope decisions and limitations |
| [Results](docs/results.md) | Full tables, trend tests, run consistency, topic and domain patterns, exploratory checks |
| [`scripts/`](scripts/) | Prompt runner and analysis scripts |
| [`data/`](data/) | Summary data |

## Reproducing the analysis

```
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...

python scripts/run_prompts.py PROMPTS.xlsx --runs 3 --out results
python scripts/analyze_refusals.py results/responses.csv --dev T21,T22,T23,T24,T25 --workbook PROMPTS.xlsx
python scripts/topic_table.py results/responses.csv PROMPTS.xlsx --dev T21,T22,T23,T24,T25
```

`PROMPTS.xlsx` holds the prompts on an `Items` sheet (`item_id`, `prompt_text`, blind depth rating) and the topics on a `Topics` sheet. The analysis scripts need only Python and openpyxl.
