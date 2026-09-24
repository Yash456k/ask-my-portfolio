"""Evaluate TypeSafe Jev as an embedding-free retrieval route.

Jev reads every chunk as plain text and ranks them. Everything after ranking is the production
path used by the embedding evaluation: the same history-aware query, candidate depth,
diversity selector, locked cases, qrel remapping, and ranking metrics.

Methods:
  hybrid  production route (app/jev.py): Choice pick first, Noul orders the rest,
          Choice "none" probability is the abstention signal
  choice  Choice only; ranks after the pick are ties, so only top-1 is meaningful
  noul    Noul per chunk only

Refusal cases are not scored for retrieval. Their abstention signal is recorded next to
the answerable cases.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from app import jev
from app.config import load_pipeline
from app.ingest import chunk_document, discover_documents
from app.retrieval_protocol import retrieval_candidate_depth, retrieval_protocol
from app.retrieval_query import build_retrieval_query
from app.retrieval_selection import select_diverse_chunks
from evaluation.eval_lib import (
    SPLITS,
    load_cases,
    load_gates,
    mean,
    ranking_metrics,
    select_cases,
    write_report,
)
from scripts.evaluate_chunking_offline import _corpus_hash
from scripts.evaluate_retrieval import aggregate_embedder_rows
from scripts.remap_evaluation_qrels import remap_cases_to_chunks


def _post(client: httpx.Client, key: str, body: dict[str, Any]) -> dict[str, Any]:
    for attempt in range(4):
        response = client.post(
            jev.JEV_ENDPOINT, json=body, headers={"Authorization": f"Bearer {key}"}
        )
        if response.status_code in {429, 503, 529} and attempt < 3:
            time.sleep(0.5 * 2**attempt)
            continue
        if response.is_error:
            detail = response.text[:300]
            raise RuntimeError(f"TypeSafe returned HTTP {response.status_code}: {detail}")
        return response.json()
    raise RuntimeError("TypeSafe unavailable after retries")


def _single_method_request(method: str, model: str, query: str, chunks: list[dict]) -> dict:
    full = jev.build_request(query, chunks, model)
    keep = (
        {jev.PICK_QUESTION} if method == "choice" else set(full["questions"]) - {jev.PICK_QUESTION}
    )
    return {**full, "questions": {k: v for k, v in full["questions"].items() if k in keep}}


def _order(method: str, result: dict, chunks: list[dict]) -> tuple[list[dict], float]:
    """Return ranked chunks and an answerable signal (higher means answerable)."""
    if method == "hybrid":
        ranking = jev.rank(result, chunks)
        return ranking.ordered, 1.0 - ranking.none_probability
    keys = [f"c{index:02d}" for index in range(1, len(chunks) + 1)]
    answers = result["answers"]
    if method == "choice":
        probabilities = answers[jev.PICK_QUESTION]["probabilities"]
        scores = [float(probabilities[key]) for key in keys]
        signal = 1.0 - float(probabilities["none"])
    else:
        scores = [float(answers[key]["noul"]) for key in keys]
        signal = max(scores)
    order = sorted(range(len(chunks)), key=lambda index: -scores[index])
    return [{**chunks[index], "score": round(scores[index], 6)} for index in order], signal


def run_method(
    *,
    client: httpx.Client,
    key: str,
    model: str,
    method: str,
    chunks: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    rows = []
    for case in cases:
        query = build_retrieval_query(
            case["question"],
            [(message["role"], message["content"]) for message in case.get("history", [])],
        )
        body = (
            jev.build_request(query, chunks, model)
            if method == "hybrid"
            else _single_method_request(method, model, query, chunks)
        )
        started = time.perf_counter()
        result = _post(client, key, body)
        elapsed_ms = (time.perf_counter() - started) * 1000
        ordered, answerable = _order(method, result, chunks)
        retrieved = select_diverse_chunks(ordered[: retrieval_candidate_depth(top_k)], top_k)
        refusal = case["answer_expectation"]["refusal"]
        rows.append(
            {
                "split": case["split"],
                "caseId": case["id"],
                "category": case["category"],
                "question": case["question"],
                "embedder": f"jev-{method}",
                "refusalCase": refusal,
                "answerableSignal": round(answerable, 6),
                "queryMs": round(elapsed_ms, 3),
                "usage": result.get("usage", {}),
                "servedModel": result.get("model"),
                "metrics": None
                if refusal
                else ranking_metrics(case["required_evidence"], retrieved),
                "retrievedChunks": [
                    {k: chunk[k] for k in ("source", "chunkIndex", "semanticId", "score")}
                    for chunk in retrieved
                ],
            }
        )
        print(
            json.dumps(
                {
                    "event": "case",
                    "method": method,
                    "case": case["id"],
                    "ms": round(elapsed_ms),
                    "recallAt5": None if refusal else rows[-1]["metrics"]["recallAt5"],
                    "answerable": round(answerable, 3),
                }
            ),
            flush=True,
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", choices=SPLITS, action="append", required=True)
    parser.add_argument(
        "--method", choices=("hybrid", "choice", "noul"), action="append", required=True
    )
    parser.add_argument("--model", default=jev.JEV_MODEL)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/results/jev"))
    args = parser.parse_args()
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise SystemExit("TYPESAFE_API_KEY is not set")

    pipeline = load_pipeline(Path("config/pipeline.yaml"))
    chunks = [
        {
            "id": str(position),
            "source": chunk.source,
            "title": chunk.title,
            "chunkIndex": chunk.index,
            "semanticId": chunk.semantic_id,
            "content": chunk.content,
        }
        for position, chunk in enumerate(
            chunk
            for document in discover_documents(Path("corpus"))
            for chunk in chunk_document(document, pipeline)
        )
    ]
    gates = load_gates()["retrieval"]
    with httpx.Client(timeout=60) as client:
        for split in args.split:
            cases = select_cases(load_cases([split]), case_ids=args.case)
            remap_cases_to_chunks([case for case in cases if case.get("required_evidence")], chunks)
            for method in args.method:
                rows = run_method(
                    client=client,
                    key=key,
                    model=args.model,
                    method=method,
                    chunks=chunks,
                    cases=cases,
                    top_k=args.top_k,
                )
                scored = [row for row in rows if not row["refusalCase"]]
                refusals = [row for row in rows if row["refusalCase"]]
                summary = {
                    "schemaVersion": 2,
                    "kind": "jev-retrieval-evaluation",
                    "split": split,
                    "method": method,
                    "requestedModel": args.model,
                    "servedModels": sorted({str(row["servedModel"]) for row in rows}),
                    "chunkCount": len(chunks),
                    "corpusSha256": _corpus_hash(
                        [{k: v for k, v in chunk.items() if k != "id"} for chunk in chunks]
                    ),
                    "topK": args.top_k,
                    "retrievalProtocol": retrieval_protocol(args.top_k),
                    "retrieval": aggregate_embedder_rows(scored, gates),
                    "abstention": {
                        "answerableMinSignal": min(row["answerableSignal"] for row in scored),
                        "refusalMaxSignal": max(row["answerableSignal"] for row in refusals)
                        if refusals
                        else None,
                        "refusalSignals": {
                            row["caseId"]: row["answerableSignal"] for row in refusals
                        },
                        "answerableMeanSignal": mean(row["answerableSignal"] for row in scored),
                    },
                    "usage": {
                        "requests": len(rows),
                        "inputTokens": sum(
                            int(row["usage"].get("input_tokens", 0) or 0) for row in rows
                        ),
                    },
                }
                summary_path, _ = write_report(
                    args.output_dir, f"jev-{method}-{split}", summary, rows
                )
                print(json.dumps({"event": "complete", "summary": str(summary_path)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
