from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import unicodedata
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.retrieval_context import format_source_excerpts

EVALUATION_ROOT = Path(__file__).resolve().parent
# Splits whose cases carry hand-written regex answer contracts.
CONTRACT_SPLITS = ("dev", "heldout", "challenge-v2")
# challenge-v3 is the large set: its answers are scored by a judge against a reference answer.
SPLITS = (*CONTRACT_SPLITS, "challenge-v3")
LOCKED_SPLITS = frozenset({"heldout", "challenge-v2", "challenge-v3"})
SECRET_KEY_PATTERN = re.compile(
    r"(?:api[-_]?key|authorization|password|secret|"
    r"(?:access|auth|verification|evaluation|bearer)?[-_]?token)$",
    re.I,
)
SECRET_VALUE_PATTERNS = (
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)(?:api[-_]?key|password|secret|token)\s*[:=]\s*\S+"),
    re.compile(r"\bgsk_[A-Za-z0-9_-]{12,}\b"),
)
CONTEXT_CHAR_BUDGETS = (1500, 2000, 2500)


class EvaluationDataError(ValueError):
    """Raised when an evaluation artifact is invalid or unexpectedly changed."""


def utc_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationDataError(f"Could not load evaluation file {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvaluationDataError(f"Evaluation file {path.name} must contain a JSON object")
    return value


def verify_split_lock(split: str, evaluation_root: Path = EVALUATION_ROOT) -> str:
    if split not in LOCKED_SPLITS:
        raise EvaluationDataError(f"Split is not lock-protected: {split}")
    split_path = evaluation_root / f"{split}.json"
    lock_path = evaluation_root / f"{split}.sha256"
    try:
        expected, filename = lock_path.read_text(encoding="ascii").strip().split(maxsplit=1)
        raw = split_path.read_bytes()
    except (OSError, ValueError) as exc:
        raise EvaluationDataError(f"{split} lock is missing or malformed") from exc
    filename = filename.lstrip("*")
    expected_filename = f"{split}.json"
    if filename != expected_filename or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise EvaluationDataError(f"{split} lock must be '<sha256>  {expected_filename}'")
    actual = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(actual, expected):
        raise EvaluationDataError(
            f"{expected_filename} changed: restore it or intentionally regenerate "
            f"{split}.sha256; "
            "never tune or train against this split"
        )
    return actual


def verify_heldout_lock(evaluation_root: Path = EVALUATION_ROOT) -> str:
    return verify_split_lock("heldout", evaluation_root)


def _validate_patterns(patterns: Sequence[str], location: str) -> None:
    if not patterns:
        raise EvaluationDataError(f"{location} must contain at least one regex")
    for pattern in patterns:
        if not isinstance(pattern, str):
            raise EvaluationDataError(f"{location} contains a non-string regex")
        try:
            re.compile(pattern, re.I | re.S)
        except re.error as exc:
            raise EvaluationDataError(f"Invalid regex in {location}: {exc}") from exc


def validate_case(case: dict[str, Any], split: str) -> None:
    case_id = case.get("id")
    if not isinstance(case_id, str) or not re.fullmatch(r"[a-z0-9-]+", case_id):
        raise EvaluationDataError(f"Invalid case id in {split}: {case_id!r}")
    if not isinstance(case.get("question"), str) or len(case["question"].strip()) < 2:
        raise EvaluationDataError(f"{case_id}: question is missing")
    if not isinstance(case.get("category"), str) or not case["category"]:
        raise EvaluationDataError(f"{case_id}: category is missing")
    history = case.get("history", [])
    if not isinstance(history, list) or len(history) > 6:
        raise EvaluationDataError(f"{case_id}: history must contain at most six messages")
    for message in history:
        if (
            not isinstance(message, dict)
            or message.get("role") not in {"user", "assistant"}
            or not message.get("content")
        ):
            raise EvaluationDataError(f"{case_id}: invalid history message")

    evidence = case.get("required_evidence", [])
    if not isinstance(evidence, list):
        raise EvaluationDataError(f"{case_id}: required_evidence must be a list")
    for group_index, group in enumerate(evidence):
        options = group.get("any_of") if isinstance(group, dict) else None
        if (
            not isinstance(group, dict)
            or not group.get("label")
            or not isinstance(options, list)
            or not options
        ):
            raise EvaluationDataError(f"{case_id}: malformed evidence group {group_index}")
        for option in options:
            if not isinstance(option.get("source"), str):
                raise EvaluationDataError(f"{case_id}: evidence option needs a source")
            indexes = option.get("chunk_indexes")
            if indexes is not None and (
                not isinstance(indexes, list)
                or not indexes
                or any(not isinstance(index, int) or index < 0 for index in indexes)
            ):
                raise EvaluationDataError(f"{case_id}: chunk_indexes must be non-negative ints")
            patterns = option.get("content_any_of", [])
            if patterns:
                _validate_patterns(patterns, f"{case_id}.required_evidence[{group_index}]")

    expectation = case.get("answer_expectation")
    if not isinstance(expectation, dict) or not isinstance(expectation.get("refusal"), bool):
        raise EvaluationDataError(f"{case_id}: answer_expectation.refusal must be boolean")
    for group_index, group in enumerate(expectation.get("claim_groups", [])):
        if not group.get("label"):
            raise EvaluationDataError(f"{case_id}: claim group {group_index} needs a label")
        _validate_patterns(group.get("any_of", []), f"{case_id}.claim_groups[{group_index}]")
    for forbidden in expectation.get("forbidden_claims", []):
        if not forbidden.get("label") or not forbidden.get("pattern"):
            raise EvaluationDataError(f"{case_id}: malformed forbidden claim")
        _validate_patterns([forbidden["pattern"]], f"{case_id}.forbidden_claims")
    if expectation["refusal"]:
        _validate_patterns(expectation.get("refusal_any_of", []), f"{case_id}.refusal_any_of")


def load_split(
    split: str,
    evaluation_root: Path = EVALUATION_ROOT,
    *,
    verify_lock: bool = True,
) -> dict[str, Any]:
    if split not in SPLITS:
        raise EvaluationDataError(f"Unknown split: {split}")
    if split in LOCKED_SPLITS and verify_lock:
        verify_split_lock(split, evaluation_root)
    payload = _load_json(evaluation_root / f"{split}.json")
    if payload.get("version") != 1 or payload.get("split") != split:
        raise EvaluationDataError(f"{split}.json has the wrong version or split")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise EvaluationDataError(f"{split}.json must contain cases")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise EvaluationDataError(f"{split}.json contains a non-object case")
        validate_case(case, split)
        if case["id"] in seen:
            raise EvaluationDataError(f"Duplicate case id: {case['id']}")
        seen.add(case["id"])
        case["split"] = split
    return payload


def load_cases(
    splits: Sequence[str],
    evaluation_root: Path = EVALUATION_ROOT,
    *,
    verify_lock: bool = True,
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for split in splits:
        for case in load_split(split, evaluation_root, verify_lock=verify_lock)["cases"]:
            if case["id"] in seen:
                raise EvaluationDataError(f"Case id is duplicated across splits: {case['id']}")
            seen.add(case["id"])
            cases.append(case)
    return cases


def load_gates(evaluation_root: Path = EVALUATION_ROOT) -> dict[str, Any]:
    gates = _load_json(evaluation_root / "gates.json")
    if gates.get("version") != 1:
        raise EvaluationDataError("gates.json has the wrong version")
    if not isinstance(gates.get("retrieval"), dict) or not isinstance(gates.get("answer"), dict):
        raise EvaluationDataError("gates.json must define retrieval and answer gates")
    return gates


def select_cases(
    cases: Sequence[dict[str, Any]],
    *,
    case_ids: Sequence[str] = (),
    categories: Sequence[str] = (),
    include_refusals: bool = True,
) -> list[dict[str, Any]]:
    requested_ids = set(case_ids)
    requested_categories = set(categories)
    known_ids = {case["id"] for case in cases}
    missing = requested_ids - known_ids
    if missing:
        raise EvaluationDataError(f"Unknown case ids: {', '.join(sorted(missing))}")
    selected = [
        case
        for case in cases
        if (not requested_ids or case["id"] in requested_ids)
        and (not requested_categories or case["category"] in requested_categories)
        and (include_refusals or not case["answer_expectation"]["refusal"])
    ]
    if not selected:
        raise EvaluationDataError("No evaluation cases matched the requested subset")
    return selected


def normalize_text(text: str) -> str:
    """Canonicalize harmless model typography before semantic contract matching."""
    normalized = unicodedata.normalize("NFKC", text).translate(
        str.maketrans(
            {
                "‐": "-",
                "‑": "-",
                "‒": "-",
                "–": "-",
                "—": "-",
                "―": "-",
                "’": "'",
                "‘": "'",
                "【": "[",
                "】": "]",
            }
        )
    )
    normalized = re.sub(r"[\u00a0\u2000-\u200b\u202f\u205f\u3000]", " ", normalized)
    normalized = re.sub(r"\s+%", "%", normalized)
    return normalized.replace("**", "")


def regex_matches(pattern: str, text: str) -> bool:
    return re.search(pattern, normalize_text(text), re.I | re.S) is not None


def evidence_option_matches(option: dict[str, Any], chunk: dict[str, Any]) -> bool:
    if chunk.get("source") != option["source"]:
        return False
    indexes = option.get("chunk_indexes")
    if indexes is not None and chunk.get("chunkIndex") not in indexes:
        return False
    patterns = option.get("content_any_of", [])
    content = str(chunk.get("content", ""))
    return not patterns or any(regex_matches(pattern, content) for pattern in patterns)


def evidence_group_ranks(
    groups: Sequence[dict[str, Any]], chunks: Sequence[dict[str, Any]]
) -> list[int | None]:
    ranks: list[int | None] = []
    for group in groups:
        rank = next(
            (
                index
                for index, chunk in enumerate(chunks, start=1)
                if any(evidence_option_matches(option, chunk) for option in group["any_of"])
            ),
            None,
        )
        ranks.append(rank)
    return ranks


def _context_redundancy(chunks: Sequence[dict[str, Any]]) -> float:
    token_sets = [
        set(re.findall(r"[a-z0-9]+", str(chunk.get("content", "")).lower())) for chunk in chunks[:5]
    ]
    similarities: list[float] = []
    for left_index, left in enumerate(token_sets):
        for right in token_sets[left_index + 1 :]:
            union = left | right
            similarities.append(0.0 if not union else len(left & right) / len(union))
    return mean(similarities)


def _context_prefix_within_budget(
    chunks: Sequence[dict[str, Any]], budget: int
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    characters = 0
    for chunk in chunks[:5]:
        candidate = [*selected, chunk]
        candidate_characters = len(format_source_excerpts(candidate))
        if candidate_characters > budget:
            break
        selected.append(chunk)
        characters = candidate_characters
        if characters >= budget:
            break
    return selected


def ranking_metrics(groups: Sequence[dict[str, Any]], chunks: Sequence[dict[str, Any]]) -> dict:
    if not groups:
        raise EvaluationDataError("Retrieval metrics require at least one evidence group")
    ranks = evidence_group_ranks(groups, chunks)
    recall = {
        f"recallAt{k}": sum(rank is not None and rank <= k for rank in ranks) / len(ranks)
        for k in (1, 3, 5)
    }
    first = min((rank for rank in ranks if rank is not None and rank <= 5), default=None)
    top_five = list(chunks[:5])
    relevant_context = sum(
        any(
            evidence_option_matches(option, chunk) for group in groups for option in group["any_of"]
        )
        for chunk in top_five
    )
    budget_metrics: dict[str, Any] = {}
    for budget in CONTEXT_CHAR_BUDGETS:
        budgeted = _context_prefix_within_budget(top_five, budget)
        budgeted_ranks = evidence_group_ranks(groups, budgeted)
        budget_metrics.update(
            {
                f"recallAt{budget}Chars": sum(rank is not None for rank in budgeted_ranks)
                / len(budgeted_ranks),
                f"allEvidenceAt{budget}Chars": all(rank is not None for rank in budgeted_ranks),
                f"contextChunksAt{budget}Chars": len(budgeted),
                f"contextCharsAt{budget}Chars": len(format_source_excerpts(budgeted)),
            }
        )
    return {
        **recall,
        **budget_metrics,
        "reciprocalRankAt5": 0.0 if first is None else 1.0 / first,
        "requiredCoveredAt5": all(rank is not None and rank <= 5 for rank in ranks),
        **{
            f"allEvidenceAt{k}": all(rank is not None and rank <= k for rank in ranks)
            for k in (1, 3, 5)
        },
        "meanReciprocalEvidenceRankAt5": mean(
            0.0 if rank is None or rank > 5 else 1.0 / rank for rank in ranks
        ),
        "meanEvidenceDiscountAt5": mean(
            0.0 if rank is None or rank > 5 else 1.0 / math.log2(rank + 1) for rank in ranks
        ),
        "requiredContextPrecisionAt5": (0.0 if not top_five else relevant_context / len(top_five)),
        "contextRedundancyAt5": _context_redundancy(top_five),
        "contextCharsAt5": len(format_source_excerpts(top_five)),
        "sourceDiversityAt5": (
            0.0
            if not top_five
            else len({str(chunk.get("source", "")) for chunk in top_five}) / len(top_five)
        ),
        "evidenceGroupRanks": ranks,
    }


def mean(values: Iterable[float]) -> float:
    materialized = list(values)
    return 0.0 if not materialized else sum(materialized) / len(materialized)


def percentile(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def sanitize_url(url: str) -> str:
    parts = urlsplit(url)
    hostname = parts.hostname or ""
    if parts.port:
        hostname = f"{hostname}:{parts.port}"
    return urlunsplit((parts.scheme, hostname, parts.path.rstrip("/"), "", ""))


def redact_text(value: str) -> str:
    redacted = value
    for pattern in SECRET_VALUE_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if SECRET_KEY_PATTERN.search(str(key)) else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def write_report(
    output_dir: Path,
    prefix: str,
    summary: dict[str, Any],
    rows: Sequence[dict[str, Any]],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = utc_timestamp()
    json_path = output_dir / f"{prefix}-{timestamp}.json"
    jsonl_path = output_dir / f"{prefix}-{timestamp}.jsonl"
    json_path.write_text(
        json.dumps(redact_sensitive(summary), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    jsonl_path.write_text(
        "".join(
            json.dumps(redact_sensitive(row), ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
    return json_path, jsonl_path
