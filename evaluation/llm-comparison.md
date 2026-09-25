# Generation model comparison

Measured 2026-09-24 with `scripts/compare_llms.py`, run inside the API image on the server.

## Method

Every model answered the same 46 locked cases (37 reached a model; Jev refused 9 locally, identically for all). Retrieval was computed once with production Jev and cached, so the model is the only variable. Prompts come from the production prompt builder and go through OpenRouter with the production payload (temperature 0.15, 600-token cap). Answers are scored by the existing answer contracts: required grounded facts, forbidden claims, valid citations, and correct refusals.

## Results

| Model | Pass | Model-answered pass | Median first token | p90 total | $/answer |
|---|---:|---:|---:|---:|---:|
| **DeepSeek V4.1 Flash** (production) | **0.870** | **0.838** | **1.5 s** | 14.6 s | $0.00025 |
| DeepSeek V4 Flash, reasoning low¹ | 0.783 | 0.730 | 2.7 s | 10.7 s | $0.00012 |
| MiMo V2.6 Flash | 0.717 | 0.649 | 5.7 s | 29.2 s | $0.00020 |
| MiMo V2.6 Pro | 0.696 | 0.622 | 3.2 s | 9.9 s | $0.00063 |
| GPT-6 Luna Pro, reasoning low¹ | 0.696 | 0.622 | 3.0 s | 4.5 s | $0.00058 |
| GPT-6 Luna | 0.652 | 0.568 | 2.7 s | 4.1 s | $0.00017 |
| GPT-OSS 20B | 0.500 | 0.378 | 3.7 s | 12.9 s | $0.00005 |
| Qwen3.7 Flash | 0.196 | 0.000 | — | — | — |

¹ With the production payload their hidden reasoning hit the 600-token cap (Luna Pro 10 times, V4 Flash 6), so they were rerun with OpenRouter `reasoning: {effort: "low"}`. Qwen3.7 Flash returned empty answers with either payload.

## Decision

Keep DeepSeek V4.1 Flash: best pass rate, fastest first token, never truncated. DeepSeek V4 Flash with low reasoning is the only credible cheaper option (half the cost, a few points lower). At current traffic the difference is cents per month, so it is not worth switching.

## Limits

- The answer contracts were written while DeepSeek V4 Flash was the production model, so their regexes likely favour DeepSeek phrasing. Reading answers side by side showed correct MiMo and Luna answers failing on wording.
- One run per model; DeepSeek V4.1 scored 0.804 and 0.870 in two runs, so treat gaps under about 6 points as noise.
- Model-level conclusions only: the blind A/B pairs on the private grading page can settle close calls by human judgment.

## Groq recheck, 2026-09-26

Re-run on the same 46 contracts after the absence-answer prompt change, with Groq models called on Groq with the production payload (scripts/compare_llms.py now does this and waits out 429s).

| Model | Pass | Model-answered pass | Median first token | p90 total |
|---|---:|---:|---:|---:|
| DeepSeek V4.1 Flash (production) | 0.848 | 0.811 | 1.4 s | 4.8 s |
| GPT-OSS 120B on Groq | 0.391 | 0.243 | 0.43 s | 1.2 s |

GPT-OSS 120B is about four times faster but fails most model-answered contracts: missing citations and claims the contracts cannot ground, written as bold headings and bullets with non-breaking hyphens. The Groq account is on the free tier (8,000 tokens a minute, about three answers a minute across all visitors), and `qwen/qwen3.6-27b` now returns 404 on Groq. DeepSeek stays the default.
