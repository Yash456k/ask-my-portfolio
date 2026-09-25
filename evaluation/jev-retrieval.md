# Jev as an embedding-free retriever

Measured 2026-09-24 with `scripts/evaluate_jev_retrieval.py --method hybrid` against TypeSafe `jev-1.13.0`.

## Method

Jev never sees an embedding. One request per question asks two things about the retrieval query:

- a **Choice** over every chunk plus "none": its pick ranks first, and the "none" probability decides whether the portfolio can answer at all;
- a **Noul** (probability of yes) per chunk: orders the remaining chunks.

Everything after ranking is the production path shared with the embedding evaluation: the same history-aware query, candidate depth, diversity selector, locked cases, qrel remapping, and scoring. Option names are neutral (`c01`, `c02`, ...), so Jev sees chunk text only. The same module (`app/jev.py`) serves production.

## Results (39 answerable cases, top 5)

| Route | R@1 | R@3 | R@5 | MRR@5 | All evidence@5 |
|---|---:|---:|---:|---:|---:|
| **Jev hybrid** | **0.949** | **0.987** | 0.987 | **1.000** | 0.974 |
| Portfolio E5 Small (best embedder) | 0.808 | 0.936 | 0.987 | 0.908 | 0.974 |
| BGE Base | 0.782 | 0.949 | 0.987 | 0.895 | 0.974 |
| Qwen3 Embedding 0.6B | 0.782 | 0.949 | 0.987 | 0.887 | 0.974 |
| Portfolio GTE Small | 0.705 | 0.897 | 0.949 | 0.824 | 0.949 |
| BGE Small | 0.692 | 0.910 | 0.974 | 0.815 | 0.974 |
| MiniLM L6 | 0.641 | 0.885 | 1.000 | 0.793 | 1.000 |

Case-weighted across dev (13), heldout (8), and challenge-v2 (18). Embedder rows are the manual-chunking arms of the 2026-08-14 rigorous reports on the same corpus (`7ddd7a8b…`, 20 chunks).

**Refusals.** On the 9 refusal and prompt-injection cases Jev's answerable signal (1 − P(none)) peaked at 0.07; on the 39 answerable cases it never fell below 0.95. Production refuses locally at P(none) ≥ 0.5, without calling a language model.

**Cost and speed.** About 6.2k input tokens per question (every chunk is sent twice), about $0.00026 at $0.042 per million tokens. Median 461 ms, p90 744 ms from the client.

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

- 39 answerable cases is a small sample. Dev and heldout informed the manual chunk boundaries (not Jev); challenge-v2, written after the chunks were frozen, is the cleanest evidence.
- Recall@5 is saturated for every route on a 20-chunk corpus; the difference is ranking quality (R@1, MRR).
- Jev reads the whole corpus per question. That works while the corpus fits TypeSafe's 32k-token state-plus-question budget and 255 options; a large corpus would need embeddings to shortlist and Jev to rerank.
- Measured before the 2026-09-24 corpus edits (Future AI Power removed; current AIVID role, graduation, and project dates added).

Rerun: `TYPESAFE_API_KEY=... python -m scripts.evaluate_jev_retrieval --split dev --split heldout --split challenge-v2 --method hybrid`
