from __future__ import annotations

import argparse
import gc
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch

from app.config import EmbedderConfig, load_pipeline
from app.embeddings import EmbeddingRegistry
from app.ingest import chunk_document, discover_documents
from app.retrieval_protocol import (
    embedding_route_protocol,
    retrieval_candidate_depth,
    retrieval_protocol,
)
from app.retrieval_query import build_retrieval_query
from app.retrieval_selection import select_diverse_chunks
from evaluation.eval_lib import (
    SPLITS,
    load_cases,
    load_gates,
    ranking_metrics,
    select_cases,
    write_report,
)
from scripts.evaluate_retrieval import aggregate_embedder_rows
from scripts.remap_evaluation_qrels import remap_cases_to_chunks


def _retrieval_query(case: dict[str, Any]) -> str:
    return build_retrieval_query(
        case["question"],
        [(message["role"], message["content"]) for message in case.get("history", [])],
    )


def _sync(device: str) -> None:
    if device.startswith("cuda"):
        torch.cuda.synchronize()


def _with_local_artifact(config: EmbedderConfig, artifact_root: Path | None) -> EmbedderConfig:
    if artifact_root is None or config.revision is not None:
        return config
    return config.model_copy(update={"model": str(artifact_root / Path(config.model).name)})


def _corpus_hash(chunks: list[dict[str, Any]]) -> str:
    canonical = json.dumps(chunks, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _abstention(rows: list[dict[str, Any]]) -> dict[str, int]:
    """How often the score threshold alone refuses, on refusal cases and on answerable ones."""
    refusals = [row for row in rows if row["refusalCase"]]
    answerable = [row for row in rows if not row["refusalCase"]]
    return {
        "refusalCases": len(refusals),
        "refusalCasesRefused": sum(row["refusedLocally"] for row in refusals),
        "answerableCases": len(answerable),
        "answerableCasesRefused": sum(row["refusedLocally"] for row in answerable),
    }


def run_model(
    *,
    pipeline,
    config: EmbedderConfig,
    chunks: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    device: str,
    top_k: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected = pipeline.model_copy(update={"embedders": [config]})
    registry = EmbeddingRegistry(selected, device=device)
    if device.startswith("cuda"):
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()

    _sync(device)
    load_started = time.perf_counter()
    registry.models[config.id] = registry._load_model(config)
    _sync(device)
    load_seconds = time.perf_counter() - load_started

    _sync(device)
    corpus_started = time.perf_counter()
    matrix = registry.encode_documents(config.id, [chunk["content"] for chunk in chunks])
    _sync(device)
    corpus_seconds = time.perf_counter() - corpus_started
    if not np.isfinite(matrix).all() or np.any(np.linalg.norm(matrix, axis=1) == 0):
        raise RuntimeError(f"{config.id}: corpus embeddings are invalid")

    rows: list[dict[str, Any]] = []
    query_times: list[float] = []
    for case in cases:
        _sync(device)
        started = time.perf_counter()
        vector = registry._encode_sync(
            registry.models[config.id],
            [_retrieval_query(case)],
            prefix=config.query_prefix,
            batch_size=1,
        )[0]
        if vector.shape[0] != config.dimensions:
            raise RuntimeError(
                f"{config.id}: query returned {vector.shape[0]} dimensions; "
                f"expected {config.dimensions}"
            )
        scores = matrix @ vector
        candidate_depth = retrieval_candidate_depth(top_k)
        order = np.argsort(-scores, kind="stable")[:candidate_depth]
        candidates = [
            {
                "id": str(index),
                "source": chunks[index]["source"],
                "title": chunks[index]["title"],
                "chunkIndex": chunks[index]["chunkIndex"],
                "semanticId": chunks[index]["semanticId"],
                "content": chunks[index]["content"],
                "score": round(float(scores[index]), 6),
            }
            for index in order
        ]
        retrieved = select_diverse_chunks(candidates, top_k)
        _sync(device)
        elapsed_ms = (time.perf_counter() - started) * 1000
        query_times.append(elapsed_ms)
        refusal = case["answer_expectation"]["refusal"]
        top_score = retrieved[0]["score"] if retrieved else None
        rows.append(
            {
                "split": case["split"],
                "caseId": case["id"],
                "category": case["category"],
                "question": case["question"],
                "embedder": config.id,
                "queryMs": round(elapsed_ms, 3),
                "refusalCase": refusal,
                "topScore": top_score,
                # Production refuses without a language model when the best match is this weak.
                "refusedLocally": top_score is None or top_score < config.minimum_score,
                "metrics": None
                if refusal
                else ranking_metrics(case["required_evidence"], retrieved),
                "retrievedChunks": retrieved,
            }
        )

    runtime = {
        "model": config.model,
        "revision": config.revision,
        "dimensions": config.dimensions,
        "device": device,
        "queryPrefix": config.query_prefix,
        "documentPrefix": config.document_prefix,
        "dtype": config.dtype,
        "minimumScore": config.minimum_score,
        "loadSeconds": round(load_seconds, 3),
        "corpusEncodeSeconds": round(corpus_seconds, 3),
        "meanQueryMs": round(sum(query_times) / len(query_times), 3),
    }
    if device.startswith("cuda"):
        runtime["peakCudaAllocatedMiB"] = round(torch.cuda.max_memory_allocated() / 1024**2, 2)
        runtime["peakCudaReservedMiB"] = round(torch.cuda.max_memory_reserved() / 1024**2, 2)

    del matrix
    del registry.models[config.id]
    del registry
    gc.collect()
    if device.startswith("cuda"):
        torch.cuda.empty_cache()
    return rows, runtime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline production-parity chunking evaluation")
    parser.add_argument("--split", choices=SPLITS, required=True)
    parser.add_argument("--chunking", choices=("auto", "manual"), required=True)
    parser.add_argument("--embedder", action="append", default=[])
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--pipeline", type=Path, default=Path("config/pipeline.yaml"))
    parser.add_argument("--corpus-dir", type=Path, default=Path("corpus"))
    parser.add_argument("--evaluation-dir", type=Path, default=Path("evaluation"))
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--no-gate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 5 <= args.top_k <= 12:
        raise SystemExit("--top-k must be between 5 and 12")
    load_pipeline.cache_clear()
    pipeline = load_pipeline(args.pipeline)
    ids = args.embedder or [config.id for config in pipeline.embedders]
    unknown = set(ids) - {config.id for config in pipeline.embedders}
    if unknown:
        raise SystemExit(f"unknown embedders: {', '.join(sorted(unknown))}")
    configs = [
        _with_local_artifact(config, args.artifact_root)
        for config in pipeline.embedders
        if config.id in ids
    ]
    documents = discover_documents(args.corpus_dir)
    built = [
        chunk
        for document in documents
        for chunk in chunk_document(
            document,
            pipeline,
            honor_manual=args.chunking == "manual",
        )
    ]
    chunks = [
        {
            "source": chunk.source,
            "title": chunk.title,
            "chunkIndex": chunk.index,
            "semanticId": chunk.semantic_id,
            "content": chunk.content,
        }
        for chunk in built
    ]
    cases = select_cases(load_cases([args.split], args.evaluation_dir))
    qrel_changes = remap_cases_to_chunks(
        [case for case in cases if not case["answer_expectation"]["refusal"]], chunks
    )
    gates = load_gates(args.evaluation_dir)["retrieval"]

    rows: list[dict[str, Any]] = []
    runtimes: dict[str, Any] = {}
    for config in configs:
        model_rows, runtime = run_model(
            pipeline=pipeline,
            config=config,
            chunks=chunks,
            cases=cases,
            device=args.device,
            top_k=args.top_k,
        )
        rows.extend(model_rows)
        runtimes[config.id] = runtime
        print(json.dumps({"event": "model-complete", "embedder": config.id, **runtime}), flush=True)

    by_embedder = {
        config.id: aggregate_embedder_rows(
            [row for row in rows if row["embedder"] == config.id and not row["refusalCase"]],
            gates,
        )
        for config in configs
    }
    abstention = {
        config.id: _abstention([row for row in rows if row["embedder"] == config.id])
        for config in configs
    }
    passed = all(result["passed"] for result in by_embedder.values())
    summary = {
        "schemaVersion": 1,
        "kind": "offline-chunking-evaluation",
        "split": args.split,
        "chunkingMode": args.chunking,
        "chunkCount": len(chunks),
        "corpusSha256": _corpus_hash(chunks),
        "caseIds": [case["id"] for case in cases if not case["answer_expectation"]["refusal"]],
        "refusalCaseIds": [case["id"] for case in cases if case["answer_expectation"]["refusal"]],
        "qrelOptionsRemapped": qrel_changes,
        "topK": args.top_k,
        "retrievalProtocol": retrieval_protocol(args.top_k),
        "embeddingRoutes": {config.id: embedding_route_protocol(config) for config in configs},
        "device": args.device,
        "gatesEnforced": not args.no_gate,
        "gates": gates,
        "embedders": by_embedder,
        "abstention": abstention,
        "runtime": runtimes,
        "passed": passed,
    }
    summary_path, details_path = write_report(
        args.output_dir,
        f"chunking-{args.chunking}-{args.split}",
        summary,
        rows,
    )
    print(
        json.dumps(
            {
                "event": "complete",
                "passed": passed,
                "summary": str(summary_path),
                "details": str(details_path),
                "embedders": by_embedder,
            },
            separators=(",", ":"),
        )
    )
    return 0 if passed or args.no_gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
