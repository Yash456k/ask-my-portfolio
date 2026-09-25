"""Compare generation models on the locked answer contracts with identical retrieval.

Retrieval runs once through the production Jev route (app/jev.py) and is cached, so every
model answers the same prompt, built by the production prompt builder, from the same
chunks. Models are called the way production calls them: Groq models on Groq, the rest
through OpenRouter, with the production payload from app/groq_client.py. Every answer is
scored by scripts.evaluate_answers.evaluate_answer. Cases Jev refuses locally never reach a model,
exactly as in production.

Run inside the API image so provider keys stay on the server:
    python -m scripts.compare_llms --model xiaomi/mimo-v2.6-flash --model openai/gpt-6-luna
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx

from app import jev
from app.config import load_pipeline
from app.groq_client import GroqClient
from app.ingest import chunk_document, discover_documents
from app.main import LOCAL_REFUSAL, SYSTEM_PROMPT, _build_user_prompt
from app.retrieval_protocol import retrieval_candidate_depth
from app.retrieval_query import build_retrieval_query
from app.retrieval_selection import select_diverse_chunks
from app.schemas import ChatRequest
from evaluation.eval_lib import SPLITS, load_cases, load_gates, select_cases
from scripts.evaluate_answers import evaluate_answer
from scripts.remap_evaluation_qrels import remap_cases_to_chunks

OPENROUTER = "https://openrouter.ai/api/v1"
TOP_K = 3  # production default


def _chunks() -> list[dict[str, Any]]:
    pipeline = load_pipeline(Path("config/pipeline.yaml"))
    built = [
        chunk
        for document in discover_documents(Path("corpus"))
        for chunk in chunk_document(document, pipeline)
    ]
    return [
        {
            "id": str(position),
            "source": chunk.source,
            "title": chunk.title,
            "chunkIndex": chunk.index,
            "semanticId": chunk.semantic_id,
            "content": chunk.content,
        }
        for position, chunk in enumerate(built)
    ]


def _retrieve(cases: list[dict], chunks: list[dict], cache: Path) -> dict[str, dict]:
    corpus = hashlib.sha256(json.dumps(chunks, sort_keys=True).encode()).hexdigest()
    if cache.exists():
        cached = json.loads(cache.read_text())
        if cached["corpus"] == corpus and set(cached["cases"]) >= {c["id"] for c in cases}:
            return cached["cases"]
    results: dict[str, dict] = {}
    headers = {"Authorization": f"Bearer {os.environ['TYPESAFE_API_KEY']}"}
    with httpx.Client(timeout=30, headers=headers) as client:
        for case in cases:
            query = build_retrieval_query(
                case["question"], [(m["role"], m["content"]) for m in case.get("history", [])]
            )
            response = client.post(jev.JEV_ENDPOINT, json=jev.build_request(query, chunks))
            response.raise_for_status()
            ranking = jev.rank(response.json(), chunks)
            depth = retrieval_candidate_depth(TOP_K)
            results[case["id"]] = {
                "chunks": select_diverse_chunks(ranking.ordered[:depth], TOP_K),
                "refuse": ranking.none_probability >= jev.NONE_REFUSAL_THRESHOLD,
            }
    cache.write_text(json.dumps({"corpus": corpus, "cases": results}))
    return results


def _provider(pipeline, model: str) -> str:
    try:
        return pipeline.llm(model).provider
    except KeyError:
        return "openrouter"  # comparison candidates not in the pipeline yet


def _prices(pipeline, models: list[str]) -> dict[str, tuple[float, float]]:
    prices = {}
    for model in models:
        if _provider(pipeline, model) == "groq":
            llm = pipeline.llm(model)
            prices[model] = (llm.input_usd_per_million / 1e6, llm.output_usd_per_million / 1e6)
    rest = [model for model in models if model not in prices]
    if rest:
        listing = httpx.get(f"{OPENROUTER}/models", timeout=30).json()["data"]
        table = {
            m["id"]: (float(m["pricing"]["prompt"]), float(m["pricing"]["completion"]))
            for m in listing
        }
        missing = [model for model in rest if model not in table]
        if missing:
            raise SystemExit(f"Not on OpenRouter: {', '.join(missing)}")
        prices.update({model: table[model] for model in rest})
    return prices


def _stream(
    client: httpx.Client, model: str, user_prompt: str, pipeline, reasoning: str | None
) -> dict[str, Any]:
    provider = _provider(pipeline, model)
    # The production payload, so each provider gets exactly what the live API sends.
    payload = GroqClient._payload(
        SimpleNamespace(pipeline=pipeline), model, SYSTEM_PROMPT, user_prompt, provider
    )
    if reasoning and provider == "openrouter":
        # Not the production payload: for models whose hidden reasoning exhausts the cap.
        payload["reasoning"] = {"effort": reasoning, "exclude": True}
    started = time.perf_counter()
    first = None
    parts: list[str] = []
    usage: dict[str, Any] = {}
    error = None
    try:
        with client.stream("POST", GroqClient.endpoints[provider], json=payload) as response:
            if response.status_code != 200:
                elapsed = round((time.perf_counter() - started) * 1000, 1)
                return {
                    "answer": "",
                    "firstTokenMs": None,
                    "totalMs": elapsed,
                    "usage": {},
                    "error": f"http_{response.status_code}",
                }
            for line in response.iter_lines():
                if not line.startswith("data:") or line.strip() == "data: [DONE]":
                    continue
                event = json.loads(line[5:])
                if event.get("error"):
                    error = str(event["error"].get("message", "stream_error"))[:200]
                for choice in event.get("choices", []):
                    text = (choice.get("delta") or {}).get("content") or ""
                    if text:
                        first = first or time.perf_counter()
                        parts.append(text)
                if event.get("usage"):
                    usage = event["usage"]
    except httpx.HTTPError as exc:
        error = type(exc).__name__
    ended = time.perf_counter()
    return {
        "answer": "".join(parts),
        "firstTokenMs": None if first is None else round((first - started) * 1000, 1),
        "totalMs": round((ended - started) * 1000, 1),
        "usage": usage,
        "error": error,
    }


def _run_model(model, cases, retrieval, pipeline, price, forbidden, reasoning) -> list[dict]:
    rows = []
    key = "GROQ_API_KEY" if _provider(pipeline, model) == "groq" else "OPENROUTER_API_KEY"
    headers = {"Authorization": f"Bearer {os.environ[key]}"}
    with httpx.Client(timeout=120, headers=headers) as client:
        for case in cases:
            retrieved = retrieval[case["id"]]
            if retrieved["refuse"]:
                result = {
                    "answer": LOCAL_REFUSAL,
                    "firstTokenMs": 0.0,
                    "totalMs": 0.0,
                    "usage": {},
                    "error": None,
                    "local": True,
                }
            else:
                request = ChatRequest(
                    question=case["question"],
                    embedder="jev",
                    model=model,
                    history=case.get("history", []),
                    topK=TOP_K,
                    useHistory=True,
                )
                prompt = _build_user_prompt(request, retrieved["chunks"])
                result = {**_stream(client, model, prompt, pipeline, reasoning), "local": False}
            prompt_tokens = int(result["usage"].get("prompt_tokens") or 0)
            completion_tokens = int(result["usage"].get("completion_tokens") or 0)
            cost = prompt_tokens * price[0] + completion_tokens * price[1]
            latencies = {
                "embeddingMs": 0.0,
                "retrievalMs": 0.0,
                "firstTokenMs": result["firstTokenMs"] or 0.0,
                "generationMs": result["totalMs"],
                "totalMs": result["totalMs"],
            }
            response = {
                "httpStatus": 200 if not result["error"] else 599,
                "streamError": result["error"],
                "done": {"latencies": latencies} if result["answer"] else None,
                "answer": result["answer"],
                "sources": retrieved["chunks"],
            }
            score = evaluate_answer(case, response, forbidden)
            rows.append(
                {
                    "model": model,
                    "caseId": case["id"],
                    "split": case["split"],
                    "question": case["question"],
                    "answer": result["answer"],
                    "localRefusal": result["local"],
                    "error": result["error"],
                    "firstTokenMs": result["firstTokenMs"],
                    "totalMs": result["totalMs"],
                    "promptTokens": prompt_tokens,
                    "completionTokens": completion_tokens,
                    "costUsd": cost,
                    "passed": score["passed"],
                    "failures": score["failures"],
                }
            )
    return rows


def _summary(model: str, rows: list[dict]) -> dict[str, Any]:
    answered = [row for row in rows if not row["localRefusal"]]
    ttft = sorted(row["firstTokenMs"] for row in answered if row["firstTokenMs"])
    totals = sorted(row["totalMs"] for row in answered)
    failures: dict[str, int] = {}
    for row in rows:
        for failure in row["failures"]:
            failures[failure] = failures.get(failure, 0) + 1
    return {
        "model": model,
        "passRate": round(sum(row["passed"] for row in rows) / len(rows), 3),
        "modelAnsweredPassRate": round(sum(r["passed"] for r in answered) / len(answered), 3),
        "cases": len(rows),
        "modelAnswered": len(answered),
        "errors": sum(1 for row in answered if row["error"] or not row["answer"]),
        "failures": failures,
        "medianFirstTokenMs": statistics.median(ttft) if ttft else None,
        "p90TotalMs": totals[int(0.9 * (len(totals) - 1))] if totals else None,
        "costPerAnswerUsd": round(sum(r["costUsd"] for r in answered) / len(answered), 7),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--reasoning-effort", choices=("minimal", "low", "medium"))
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/results/llm"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    pipeline = load_pipeline(Path("config/pipeline.yaml"))
    chunks = _chunks()
    cases = select_cases(load_cases(list(SPLITS)))
    remap_cases_to_chunks([case for case in cases if case.get("required_evidence")], chunks)
    retrieval = _retrieve(cases, chunks, args.output_dir / "retrieval-cache.json")
    prices = _prices(pipeline, args.model)
    forbidden = load_gates()["answer"]["globalForbiddenClaims"]

    with ThreadPoolExecutor(max_workers=len(args.model)) as pool:
        futures = {
            model: pool.submit(
                _run_model,
                model,
                cases,
                retrieval,
                pipeline,
                prices[model],
                forbidden,
                args.reasoning_effort,
            )
            for model in args.model
        }
        results = {model: future.result() for model, future in futures.items()}

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    summaries = [_summary(model, rows) for model, rows in results.items()]
    for summary in summaries:
        summary["reasoningEffort"] = args.reasoning_effort
    summaries.sort(key=lambda s: (-s["passRate"], s["costPerAnswerUsd"]))
    (args.output_dir / f"compare-{stamp}.json").write_text(json.dumps(summaries, indent=2))
    with (args.output_dir / f"compare-{stamp}.jsonl").open("w") as handle:
        for rows in results.values():
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"stamp": stamp, "summaries": summaries}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
