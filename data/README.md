# Data

Summary data from the pilot. Prompt text and raw API responses are not included; prompt text is available to researchers on request.

## `prompt_outcomes.csv`

One row per prompt (75 rows). Every number on the landing page and in the results can be reproduced from this file.

| Column | Meaning |
| --- | --- |
| `item_id` | Prompt ID, `TOPIC-LEVEL` (for example `T01-L2`) |
| `topic_id` | Topic ID (T01–T25) |
| `domain` | One of five topic domains |
| `level` | Depth level: L1 less technical, L2 more technical, L3 highly technical |
| `prompt_set` | `main` (60 prompts) or `development` (15 prompts, topics T21–T25) |
| `input_tokens` | Prompt length in input tokens, as reported by the API |
| `blind_depth_rating` | Expert's blind depth rating, 1 (news level) to 5 (specialist) |
| `refused_runs` | Number of runs the safety classifier refused (0–3) |
| `runs` | Number of runs (3) |

## `refusal_summary.csv`

Refusal counts and rates by level, prompt set and run, with 95% Wilson confidence intervals. Output of [`scripts/analyze_refusals.py`](../scripts/analyze_refusals.py) run with `--dev T21,T22,T23,T24,T25`.
