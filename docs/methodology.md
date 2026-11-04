# Methodology: depth vs harm pilot

Eduardo A González, PhD · November 2026 · [Results](results.md) · [Summary](../README.md)

## Research question

Does Claude's API safety classifier conflate technical depth with practical harm? The study asks whether, on benign chemical-threat questions with no practical uplift, the classifier refuses more often as the technical depth of the question rises.

The system tested is Claude as deployed through the API: the model together with its safety classifier. The primary outcome is the classifier's decision. How the model itself answers is recorded as observation only.

## Prompt set

- **Topics:** 25 benign chemical-threat topics chosen by the expert (PhD, chemical threat toxicology).
- **Depth levels:** each topic is written at three levels. L1 is less technical (general public), L2 is more technical (college students), and L3 is highly technical (clinicians or researchers). That gives 75 prompts.
- **Drafting:** prompts were drafted by OpenAI GPT-6 through the ChatGPT interface, reasoning effort Medium, on 2026-10-28. The drafting model was used only for drafting and is not a tested model. Using a different provider avoids having Claude write the prompts it is tested on.
- **Expert review:** the expert reviewed every prompt before any model run.

## Inclusion screen

Each prompt passed two yes/no checks by the expert before inclusion:

1. **No practical uplift:** the prompt asks for nothing beyond what public educational references already provide.
2. **Legitimate need:** the question is one a student, clinician, emergency responder or member of the public could plausibly ask.

Prompts that failed either check were replaced. No scales were used for uplift or need.

## Depth check

The expert rated each prompt's technical depth blind, in shuffled order with topic and level hidden. The check is that rated depth rises from L1 to L3, confirming the levels differ as intended.

## Development set

Five of the 25 topics (15 prompts) were first run once on their own to test the workflow: the runner script, the output files and the blinding steps. The expert saw their classifier refusal counts. No grading criteria were changed as a result.

These 15 prompts were then rerun fresh with the other 60, as one shuffled batch under identical conditions. Only the fresh run is used in the results. The earlier development responses are not. The development topics were first labeled broadly and were assigned to the five main-set domains after the run, by topic content only.

## Model and settings

- **Responding model:** Claude Opus 5.5 (claude-opus-5-5) through the Anthropic API. The model ID returned by the API is recorded for every response.
- **Conversation:** one fresh single-turn request per prompt, with no system prompt and no conversation history.
- **Sampling:** no sampling parameters are set, because the model doesn't accept them, so the API defaults apply.
- **Effort:** set explicitly to medium, the API default. Thinking can't be turned off on this model.
- **Output limit:** 16,000 tokens.
- **Refusal fallbacks:** disabled. A fallback would answer a refused prompt with a different model and hide the refusals being measured.
- **Order:** the 75 prompts are sent in a randomized order with a fixed seed (20261028).
- **Records:** every response is saved, refusals included, with its stop reason, classifier category, token counts, request ID and timestamp. The runner is [`scripts/run_prompts.py`](../scripts/run_prompts.py).

## Runs

Each prompt is run three times, as separate fresh requests, for 225 responses. Run 1 was collected first. Runs 2 and 3 were added afterwards with the same script, settings and workbook, and only the classifier outcome is used from any run.

## Outcome

- **Classifier refusal:** the API returns stop_reason "refusal" when its safety classifier declines a request. This is recorded automatically and needs no judgment, so blinding doesn't affect it. The classifier category is recorded too.

## Analysis

- **Primary:** classifier refusal rate by depth level, with 95% confidence intervals, and a within-topic permutation test for trend across L1, L2 and L3. Level labels are shuffled within each topic (100,000 shuffles), with each prompt's three runs kept together, so topic and repeated runs are respected. A Cochran–Armitage trend test on all responses is reported alongside it. A mixed-effects logistic regression was planned but isn't used, because L1 had almost no refusals (1 of 75), which makes that model's estimates unstable. Run-to-run consistency and per-topic patterns are reported descriptively. The script is [`scripts/analyze_refusals.py`](../scripts/analyze_refusals.py).
- **Answer to the question:** the classifier conflates depth with harm if refusals rise significantly with depth on prompts the expert judged to carry no uplift.
- **Supporting lines:** the 60 non-development prompts alone, and the 15 development prompts alone, reported descriptively to show the trend holds either way.

**Optional exploratory checks (depth confound):** the plan specified descriptive comparisons, discussed only if they showed something useful. After data collection, permutation tests were added for these checks and are reported as exploratory. Within each level, they compare refused and answered prompts on prompt length (input tokens) and on the expert's blind depth rating. They give a first look at whether refusals follow depth itself or features that come with it, such as length. Separating those properly needs matched prompts that change one feature at a time, which is left for future work.

## Observations

The expert reads the responses that passed the classifier and notes any hedging, caution or model-written refusals. These are reported anecdotally and aren't coded or tested. They are not reported in this version and may be added in a later update.

## Scope decisions

The following were planned at first and cut from scope:

- outcome coding of answered responses (Full, Hedged, Redirect, Refusal)
- quality scores, flags and refusal rationale codes
- scaled uplift and need ratings

The reason is time. The pilot was scoped to 1–2 weeks, and the classifier refusals answer the core question without subjective coding.

## Limitations

- **Single expert:** one expert chose the topics, screened the prompts and rated depth, with no second rater. Adding one is the first extension for future work.
- **Small sample:** 25 topics at three levels, three runs each, and the classifier was almost deterministic, so the effective sample is 75 prompts.
- **Not pre-registered:** the design was settled before any main-run data was collected, but it wasn't formally pre-registered.
- **Development topics included:** five topics were used to develop the workflow before being rerun with the main set.
- **One model and one point in time:** classifiers and models change, so results apply to this model ID on these dates.
- **Depth, length and specificity:** deeper questions are also longer and more specific, so depth can't be fully separated from these variables. Each topic's three prompts concern the same agent, which holds the agent constant but not the specificity of what is asked. Exploratory checks at matched lengths are in the results. A follow-up study would add short prompts (about 32–50 tokens) rated 4–5, and pairs that keep depth fixed while varying specificity.
