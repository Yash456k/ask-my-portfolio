# Portfolio RAG evaluation

This directory defines deterministic retrieval qrels and answer contracts for questions a
recruiter, interviewer, or hiring manager might ask. `dev.json` is available for training-data
review, failure analysis, and threshold calibration. `heldout.json` remains checksum-locked, but
it was used against multiple manual-chunk candidates during the 2026-08-14 iteration. Treat its
results as regression evidence, not as an untouched estimate of generalization.

`challenge-v2.json` is the replacement post-deployment challenge. Its 22 cases were authored only
after the final 20-chunk candidate was frozen, qrels were remapped without looking at retrieval
scores, and the file was sealed in `challenge-v2.sha256` before its first run. The first
six-embedder run completed on 2026-08-14 and is preserved in
`manual-chunking-challenge-v2-rigorous.{json,md}`. It is now ordinary regression data: do not tune
chunking, qrels, gates, or model settings against that result.

`challenge-v3.json` is the large set: 276 cases (225 answerable, 51 that must be refused) written
by Claude Sonnet agents and labelled blind by separate ones, under the rules in
`challenge-v3-rules/`. `challenge-v3-provenance.json` records, for every case, what the writer
and the labeller each chose and how disagreements were settled. It was sealed in
`challenge-v3.sha256` before its first run on 2026-10-04 and is now regression data. Its cases
carry a `reference_answer` instead of regex answer contracts, so the answer scripts that depend
on contracts skip it. `scripts.summarize_retrieval_runs` pools Jev and embedding runs into one
comparison with bootstrap intervals and paired sign tests; the result is
`retrieval-comparison-challenge-v3.json` and the write-up is `retrieval-challenge-v3.md`.

`scripts.judge_answers` grades the answers `evaluate_answers` collects on challenge-v3, against each
case's reference answer and the sources the chat was shown, and `scripts.judge_agreement` compares
those grades with a person's from the grading page. The first full run is written up in
`answers-challenge-v3.md`, with every answer and verdict in `answers-challenge-v3.judged.jsonl`.

Each factual case contains source-and-chunk evidence groups. A qrel option combines a source,
the current deterministic chunk indexes, and a section-specific content regex. The regex prevents
an overlapping but wrong section from counting and makes intentional re-chunking easy to review.
Answer contracts use regex alternatives instead of exact prose, require cited retrieved evidence,
and reject stale or fabricated claims. Refusal cases test unsupported requests and prompt
injection. The suite also contains misspellings and conversation-history follow-ups.

Locked split checksums are verified automatically whenever those splits are loaded. Changing a
locked file without an intentional qrel remap and lock update fails closed. If a corpus edit
changes chunk indexes, review qrels against `app.ingest.chunk_document`; do not relax claims based
on model outputs.

Run retrieval evaluation inside an environment that has the configured model artifacts and the
ingested PostgreSQL database:

```bash
python -m scripts.evaluate_retrieval --split challenge-v2
```

The command emits a JSON summary and JSONL case records. Gates apply independently to every
embedder. Reports include Recall@1/3/5, first-hit MRR@5, mean reciprocal evidence rank, complete
evidence success, required-context precision, context redundancy/size, and fixed 1,500/2,000/2,500
character-budget retrieval metrics. DB-backed and offline evaluation both retrieve the shared
candidate depth and then apply `select_diverse_chunks`, matching production. Context budgets count
the exact production-formatted source excerpts and never exceed the ceiling.

Use `scripts.compare_chunking_runs` for strict automatic-versus-manual pairing, deterministic
paired bootstrap intervals, exact sign tests, corpus-hash validation, category views, and
evidence-level regression lists. Challenge comparisons also include a shared-fact cluster-bootstrap
sensitivity view. Fresh offline summaries serialize candidate depth, ranking, query-builder,
diversity-selector settings, and complete embedding-route settings so the comparator can reject
protocol mismatches. Preserved 2026-08-14 source reports predate those fields; their generated
comparisons mark this limitation instead of claiming artifact-level proof. Use
`scripts.compare_answer_runs` for full-request paired answer quality. Provider failures and
fallbacks are excluded; completed local refusals remain scored quality outcomes.

Run live answer evaluation against a reachable API. The default selection comes from `/v1/config`;
repeat `--embedder` or `--model` to compare routes. `--case`, `--category`, `--split`, and `--runs`
support focused and repeated checks. A request budget prevents accidentally exhausting the public
daily rate limit.

```bash
python -m scripts.evaluate_answers \
  --base-url https://api.example.test \
  --split dev --runs 2
```

For operator-only repeated runs, set `RAG_EVALUATION_TOKEN` in the evaluator process to the
server verification value. The evaluator sends it only in `X-Verify-Evaluation`, never serializes
the header or value, and the browser CORS policy does not permit this header.

Answer JSONL records include the full answer, retrieved chunks and scores, event counts, usage,
requested/served model, fallback attempts, and all stage latencies. They never persist request
headers, environment variables, database URLs, provider keys, or URL credentials. Quality gates
cover completion, expected grounded claims, refusals, forbidden claims, and valid citations that
actually point to required evidence.

Generated reports live under `evaluation/results/` and are ignored by Git.
