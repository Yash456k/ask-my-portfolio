from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.eval_lib import (  # noqa: E402
    CONTRACT_SPLITS,
    EVALUATION_ROOT,
    SPLITS,
    EvaluationDataError,
    evidence_group_ranks,
    evidence_option_matches,
    load_cases,
    load_gates,
    mean,
    normalize_text,
    percentile,
    redact_sensitive,
    regex_matches,
    sanitize_url,
    select_cases,
    write_report,
)

DEFAULT_REFUSAL_PATTERN = r"I can only answer questions supported by Yash(?:'|’)?s portfolio corpus"
REQUIRED_LATENCIES = {
    "embeddingMs",
    "retrievalMs",
    "firstTokenMs",
    "generationMs",
    "totalMs",
}


def parse_sse(lines: Iterable[str]) -> Iterator[dict[str, Any]]:
    """Parse data fields from an SSE stream without retaining raw token frames."""
    data: list[str] = []
    for line in lines:
        if line == "":
            if data:
                try:
                    event = json.loads("\n".join(data))
                except json.JSONDecodeError as exc:
                    raise EvaluationDataError("The API returned malformed SSE JSON") from exc
                if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                    raise EvaluationDataError("The API returned an SSE event without a type")
                yield event
                data = []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if field == "data":
            data.append(value[1:] if value.startswith(" ") else value)
    if data:
        try:
            event = json.loads("\n".join(data))
        except json.JSONDecodeError as exc:
            raise EvaluationDataError("The API returned truncated SSE JSON") from exc
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise EvaluationDataError("The API returned an SSE event without a type")
        yield event


def _safe_http_error(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"status": response.status_code, "detail": "non_json_error_response"}
    detail = payload.get("detail") if isinstance(payload, dict) else None
    return {
        "status": response.status_code,
        "detail": redact_sensitive(detail) if detail is not None else "request_failed",
    }


def stream_chat(
    client: httpx.Client,
    base_url: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    endpoint = f"{base_url.rstrip('/')}/v1/chat"
    headers = {"Accept": "text/event-stream", "Content-Type": "application/json"}
    evaluation_token = os.environ.get("RAG_EVALUATION_TOKEN")
    if evaluation_token:
        # This operator-only header bypasses counters for repeated evaluation. It is never logged.
        headers["X-Verify-Evaluation"] = evaluation_token
    event_counts: Counter[str] = Counter()
    answer_parts: list[str] = []
    sources: list[dict[str, Any]] = []
    meta: dict[str, Any] | None = None
    model: dict[str, Any] | None = None
    usage: list[Any] = []
    done: dict[str, Any] | None = None
    stream_error: dict[str, Any] | None = None

    with client.stream(
        "POST",
        endpoint,
        headers=headers,
        json=payload,
    ) as response:
        if response.status_code != 200:
            response.read()
            return {
                "httpStatus": response.status_code,
                "httpError": _safe_http_error(response),
                "eventCounts": {},
                "answer": "",
                "sources": [],
                "meta": None,
                "model": None,
                "usage": [],
                "done": None,
                "streamError": None,
            }
        for event in parse_sse(response.iter_lines()):
            event_type = event["type"]
            event_counts[event_type] += 1
            if event_type == "token":
                answer_parts.append(str(event.get("token", "")))
            elif event_type == "sources":
                chunks = event.get("chunks")
                sources = chunks if isinstance(chunks, list) else []
            elif event_type == "meta":
                meta = event
            elif event_type == "model":
                model = event
            elif event_type == "usage":
                usage.append(event.get("usage"))
            elif event_type == "done":
                done = event
            elif event_type == "error":
                stream_error = event

    return {
        "httpStatus": 200,
        "httpError": None,
        "eventCounts": dict(event_counts),
        "answer": "".join(answer_parts).strip(),
        "sources": sources,
        "meta": meta,
        "model": model,
        "usage": usage,
        "done": done,
        "streamError": stream_error,
    }


def _claim_group_results(groups: Sequence[dict[str, Any]], answer: str) -> list[dict[str, Any]]:
    return [
        {
            "label": group["label"],
            "matched": any(regex_matches(pattern, answer) for pattern in group["any_of"]),
        }
        for group in groups
    ]


def _forbidden_results(forbidden: Sequence[dict[str, Any]], answer: str) -> list[dict[str, Any]]:
    return [
        {
            "label": item["label"],
            "matched": regex_matches(item["pattern"], answer),
        }
        for item in forbidden
    ]


def _citation_results(
    case: dict[str, Any], answer: str, sources: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    expectation = case["answer_expectation"]
    normalized_answer = normalize_text(answer)
    cited = [int(value) for value in re.findall(r"\[S(\d+)\]", normalized_answer, re.I)]
    unique = sorted(set(cited))
    malformed = re.findall(r"\[S[^\]]*\]", re.sub(r"\[S\d+\]", "", normalized_answer), re.I)
    valid = not malformed and all(1 <= index <= len(sources) for index in unique)
    cited_chunks = [sources[index - 1] for index in unique if 1 <= index <= len(sources)]
    group_support = [
        any(
            evidence_option_matches(option, chunk)
            for chunk in cited_chunks
            for option in group["any_of"]
        )
        for group in case["required_evidence"]
    ]
    minimum = int(expectation.get("min_citations", 0))
    maximum = expectation.get("max_citations")
    count_pass = len(unique) >= minimum and (maximum is None or len(unique) <= maximum)
    evidence_cited = all(group_support)
    return {
        "citedSourceNumbers": unique,
        "malformed": malformed,
        "allReferencesValid": valid,
        "requiredEvidenceCited": evidence_cited,
        "evidenceGroupCitationSupport": group_support,
        "minimumRequired": minimum,
        "maximumAllowed": maximum,
        "passed": valid and count_pass and evidence_cited,
    }


def evaluate_answer(
    case: dict[str, Any],
    response: dict[str, Any],
    global_forbidden: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    answer = response.get("answer", "")
    sources = response.get("sources", [])
    done = response.get("done")
    latencies = done.get("latencies", {}) if isinstance(done, dict) else {}
    completed = (
        response.get("httpStatus") == 200
        and response.get("streamError") is None
        and isinstance(done, dict)
        and bool(answer)
        and isinstance(sources, list)
        and REQUIRED_LATENCIES.issubset(latencies)
    )
    expectation = case["answer_expectation"]
    claim_results = _claim_group_results(expectation.get("claim_groups", []), answer)
    forbidden_results = _forbidden_results(
        [*global_forbidden, *expectation.get("forbidden_claims", [])], answer
    )
    evidence_ranks = evidence_group_ranks(case["required_evidence"], sources)
    evidence_covered = all(rank is not None and rank <= 5 for rank in evidence_ranks)

    if expectation["refusal"]:
        refusal_pass = any(
            regex_matches(pattern, answer) for pattern in expectation["refusal_any_of"]
        )
    else:
        refusal_pass = not regex_matches(DEFAULT_REFUSAL_PATTERN, answer)
    claim_pass = all(item["matched"] for item in claim_results)
    forbidden_pass = not any(item["matched"] for item in forbidden_results)
    citation = _citation_results(case, answer, sources)
    grounded_claim_pass = claim_pass and evidence_covered

    gates = {
        "completion": completed,
        "groundedClaim": grounded_claim_pass,
        "refusal": refusal_pass,
        "forbiddenClaim": forbidden_pass,
        "citation": citation["passed"],
    }
    failures = [name for name, passed in gates.items() if not passed]
    return {
        "passed": not failures,
        "gates": gates,
        "failures": failures,
        "claimGroups": claim_results,
        "forbiddenClaims": forbidden_results,
        "evidenceGroupRanks": evidence_ranks,
        "citation": citation,
    }


def aggregate_answer_rows(rows: Sequence[dict[str, Any]], gates: dict[str, Any]) -> dict[str, Any]:
    if not rows:
        raise EvaluationDataError("Cannot aggregate an empty answer result")
    latencies = [
        float(row["response"]["done"]["latencies"]["totalMs"])
        for row in rows
        if isinstance(row["response"].get("done"), dict)
        and isinstance(row["response"]["done"].get("latencies"), dict)
        and isinstance(row["response"]["done"]["latencies"].get("totalMs"), int | float)
    ]
    pass_rate = mean(float(row["evaluation"]["passed"]) for row in rows)
    completion_rate = mean(float(row["evaluation"]["gates"]["completion"]) for row in rows)
    p95 = percentile(latencies, 0.95)
    metrics = {
        "requestCount": len(rows),
        "passRate": round(pass_rate, 6),
        "completionRate": round(completion_rate, 6),
        "fallbackRate": round(
            mean(
                float(bool((row["response"].get("done") or {}).get("fallbackUsed"))) for row in rows
            ),
            6,
        ),
        "meanTotalMs": None if not latencies else round(mean(latencies), 3),
        "p95TotalMs": None if p95 is None else round(p95, 3),
    }
    failures = []
    if metrics["passRate"] < gates["minPassRate"]:
        failures.append("minPassRate")
    if metrics["completionRate"] < gates["minCompletionRate"]:
        failures.append("minCompletionRate")
    if metrics["p95TotalMs"] is None or metrics["p95TotalMs"] > gates["maxP95TotalMs"]:
        failures.append("maxP95TotalMs")
    if gates.get("requireAllSafetyCases") and any(
        row["category"] in {"refusal", "prompt-injection"} and not row["evaluation"]["passed"]
        for row in rows
    ):
        failures.append("requireAllSafetyCases")
    if gates.get("requireNoForbiddenClaims") and any(
        not row["evaluation"]["gates"]["forbiddenClaim"] for row in rows
    ):
        failures.append("requireNoForbiddenClaims")
    return {**metrics, "gateFailures": failures, "passed": not failures}


def _validate_base_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise EvaluationDataError("--base-url must be an absolute HTTP(S) URL")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise EvaluationDataError("--base-url cannot contain credentials, query, or fragment")
    return base_url.rstrip("/")


def _resolve_selections(
    client: httpx.Client,
    base_url: str,
    embedders: Sequence[str],
    models: Sequence[str],
) -> tuple[list[str], list[str]]:
    if embedders and models:
        return list(dict.fromkeys(embedders)), list(dict.fromkeys(models))
    response = client.get(f"{base_url}/v1/config")
    if response.status_code != 200:
        raise EvaluationDataError("Could not resolve defaults from /v1/config")
    payload = response.json()
    defaults = payload.get("defaults", {})
    return (
        list(dict.fromkeys(embedders)) or [defaults["embedder"]],
        list(dict.fromkeys(models)) or [defaults["llm"]],
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Grade live POST SSE portfolio answers against hiring-question contracts"
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--split", choices=[*SPLITS, "all"], default="all")
    parser.add_argument("--embedder", action="append", default=[])
    parser.add_argument("--model", action="append", default=[])
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--category", action="append", default=[])
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--delay-seconds", type=float, default=0.1)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--request-budget", type=int, default=50)
    parser.add_argument(
        "--shuffle-seed",
        type=int,
        help="Ask the cases in a seeded random order, so the newest logged answers are a "
        "random sample for hand grading",
    )
    parser.add_argument("--evaluation-dir", type=Path, default=EVALUATION_ROOT)
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/results"))
    parser.add_argument("--no-gate", action="store_true")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    base_url = _validate_base_url(args.base_url)
    if not 1 <= args.runs <= 100:
        raise EvaluationDataError("--runs must be between 1 and 100")
    if not 0 <= args.delay_seconds <= 60:
        raise EvaluationDataError("--delay-seconds must be between 0 and 60")
    if not 5 <= args.timeout_seconds <= 300:
        raise EvaluationDataError("--timeout-seconds must be between 5 and 300")

    splits = list(CONTRACT_SPLITS) if args.split == "all" else [args.split]
    cases = select_cases(
        load_cases(splits, args.evaluation_dir),
        case_ids=args.case,
        categories=args.category,
    )
    if args.shuffle_seed is not None:
        random.Random(args.shuffle_seed).shuffle(cases)  # noqa: S311 (ordering, not security)
    gate_config = load_gates(args.evaluation_dir)["answer"]
    global_forbidden = gate_config.get("globalForbiddenClaims", [])

    rows: list[dict[str, Any]] = []
    with httpx.Client(timeout=args.timeout_seconds, follow_redirects=True) as client:
        embedders, models = _resolve_selections(client, base_url, args.embedder, args.model)
        requested = len(cases) * len(embedders) * len(models) * args.runs
        if requested > args.request_budget:
            raise EvaluationDataError(
                f"Evaluation needs {requested} requests, above --request-budget "
                f"{args.request_budget}; select a subset or explicitly raise the budget"
            )
        request_number = 0
        for run_number in range(1, args.runs + 1):
            for embedder in embedders:
                for model in models:
                    for case in cases:
                        request_number += 1
                        payload = {
                            "question": case["question"],
                            "embedder": embedder,
                            "model": model,
                            "history": case.get("history", []),
                        }
                        try:
                            response = stream_chat(client, base_url, payload)
                        except (httpx.HTTPError, EvaluationDataError) as exc:
                            response = {
                                "httpStatus": None,
                                "transportError": type(exc).__name__,
                                "eventCounts": {},
                                "answer": "",
                                "sources": [],
                                "meta": None,
                                "model": None,
                                "usage": [],
                                "done": None,
                                "streamError": None,
                            }
                        evaluation = evaluate_answer(case, response, global_forbidden)
                        rows.append(
                            {
                                "split": case["split"],
                                "caseId": case["id"],
                                "category": case["category"],
                                "run": run_number,
                                "requestNumber": request_number,
                                "request": payload,
                                "response": response,
                                "evaluation": evaluation,
                            }
                        )
                        if request_number < requested and args.delay_seconds:
                            time.sleep(args.delay_seconds)

    combinations = {}
    for embedder in embedders:
        for model in models:
            key = f"{embedder}::{model}"
            combinations[key] = aggregate_answer_rows(
                [
                    row
                    for row in rows
                    if row["request"]["embedder"] == embedder and row["request"]["model"] == model
                ],
                gate_config,
            )
    passed = all(result["passed"] for result in combinations.values())
    summary = {
        "schemaVersion": 1,
        "kind": "answer-evaluation",
        "baseUrl": sanitize_url(base_url),
        "splits": splits,
        "caseIds": [case["id"] for case in cases],
        "runs": args.runs,
        "embedders": embedders,
        "models": models,
        "gatesEnforced": not args.no_gate,
        "gates": {
            key: value for key, value in gate_config.items() if key != "globalForbiddenClaims"
        },
        "combinations": combinations,
        "passed": passed,
    }
    json_path, jsonl_path = write_report(args.output_dir, "answers", summary, rows)
    print(
        json.dumps(
            {
                "passed": passed,
                "summary": str(json_path),
                "details": str(jsonl_path),
                "combinations": combinations,
            },
            separators=(",", ":"),
        )
    )
    return 0 if passed or args.no_gate else 1


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except EvaluationDataError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        # Never print arbitrary server or transport errors; they can contain credentials.
        print(
            json.dumps({"error": "answer_evaluation_failed", "type": type(exc).__name__}),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
