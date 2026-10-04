# Jev as an embedding-free retriever

> A larger comparison on 276 questions is in [retrieval-challenge-v3.md](retrieval-challenge-v3.md). This page is the earlier set of 37 questions.

Measured 2026-10-04 with `scripts/evaluate_jev_retrieval.py --method hybrid` against TypeSafe `jev-1.13.0`, on the 20-passage corpus of that date (`ae1ffc04…`). The six embedding models were run the same day on the same corpus and questions with `scripts/evaluate_chunking_offline.py`. Every number below is in [retrieval-comparison-2026-10-04.json](retrieval-comparison-2026-10-04.json).

## Method

Jev never sees an embedding. One request per question asks two things about the retrieval query:

- a **Choice** over every chunk plus "none": its pick ranks first, and the "none" probability decides whether the portfolio can answer at all;
- a **Noul** (probability of yes) per chunk: orders the remaining chunks.

Everything after ranking is the production path shared with the embedding evaluation: the same history-aware query, candidate depth, diversity selector, locked cases, qrel remapping, and scoring. Option names are neutral (`c01`, `c02`, ...), so Jev sees chunk text only. The same module (`app/jev.py`) serves production.

## Results (37 answerable cases, top 5)

| Route | R@1 | R@3 | R@5 | MRR@5 | All evidence@5 |
|---|---:|---:|---:|---:|---:|
| **Jev hybrid** | **0.946** | **0.986** | 0.986 | **1.000** | 0.973 |
| BGE Base | 0.824 | 0.959 | 0.959 | 0.905 | 0.946 |
| Portfolio E5 Small (fine-tuned) | 0.811 | 0.959 | 0.986 | 0.923 | 0.973 |
| Qwen3 Embedding 0.6B | 0.716 | 0.946 | 0.986 | 0.863 | 0.973 |
| BGE Small | 0.703 | 0.905 | 0.973 | 0.832 | 0.973 |
| MiniLM L6 | 0.676 | 0.865 | 1.000 | 0.800 | 1.000 |
| Portfolio GTE Small (fine-tuned) | 0.608 | 0.919 | 0.946 | 0.776 | 0.946 |

Case-weighted across dev (12), heldout (7), and challenge-v2 (18).

**How sure is the gap.** With 37 questions the intervals are wide. Jev's R@1 has a 95% bootstrap interval of 0.89 to 0.99; BGE Base's is 0.70 to 0.93. Compared question by question, Jev beats BGE Base on R@1 by 0.12 (95% interval 0.03 to 0.23): it ranked better on 5 questions and worse on none. Against Portfolio E5 Small the gap is 0.14 (0.03 to 0.24), also 5 better and none worse.

**Refusals.** On the 9 refusal and prompt-injection cases Jev's answerable signal (1 − P(none)) peaked at 0.33 (a salary question); on the 37 answerable cases it never fell below 0.97. Production refuses locally at P(none) ≥ 0.5, without calling a language model, so all 9 were refused.

**Cost and speed.** About 6.4k input tokens per question (every chunk is sent twice), about $0.00027 at $0.042 per million tokens. Median 441 ms, p90 559 ms from the client.

## Pick wording, 2026-09-26

The pick question used to say "pick none only if no passage contains information that answers it", so "Has Yash worked at Google?" was refused: no passage mentions Google. It now lets a passage count when the answer follows from what it leaves out (a list of where he has worked answers whether he worked somewhere else) and saves "none" for questions whose topic no passage covers. Re-measured on the current corpus with both wordings side by side:

| | Before | After |
|---|---:|---:|
| Recall@1 (dev / heldout / challenge-v2) | 0.958 / 1.000 / 0.917 | 0.958 / 1.000 / 0.917 |
| MRR@5, every split | 1.000 | 1.000 |
| Lowest answerable signal | 0.96 | 0.98 |
| Highest refusal-case signal (refused below 0.5) | 0.07 | 0.36 (salary) |

All 9 refusal and prompt-injection cases are still refused, with less margin. Probe questions outside the locked set: "Has Yash worked at Google?", "…at Microsoft?", and "Does Yash know Rust?" moved from refused to answered; a favourite-movie question, a cat poem, and a prompt-injection attempt stayed refused (none probability 0.95–1.00).

## Limits

- 37 answerable cases is a small sample, which is why the intervals above are wide. Dev and heldout informed the manual chunk boundaries (not Jev); challenge-v2, written after the chunks were frozen, is the cleanest evidence.
- Recall@5 is saturated for every route on a 20-chunk corpus; the difference is ranking quality (R@1, MRR).
- Jev reads the whole corpus per question. That works while the corpus fits TypeSafe's 32k-token state-plus-question budget and 255 options; a large corpus would need embeddings to shortlist and Jev to rerank.
- An earlier run on 2026-09-24 used 39 answerable cases. Two of them asked about Future AI Power, and were removed with that project the same day, so the numbers here replace it.

Rerun: `TYPESAFE_API_KEY=... python -m scripts.evaluate_jev_retrieval --split dev --split heldout --split challenge-v2 --method hybrid`
