from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ingest import chunk_document, discover_documents
from evaluation.eval_lib import (
    EVALUATION_ROOT,
    EvaluationDataError,
    evidence_group_ranks,
    load_cases,
    regex_matches,
    verify_heldout_lock,
    verify_split_lock,
)
from scripts.remap_evaluation_qrels import remap_cases_to_chunks


def test_locked_heldout_and_required_robustness_cases_exist() -> None:
    digest = verify_heldout_lock()
    challenge_digest = verify_split_lock("challenge-v2")
    cases = load_cases(["dev", "heldout", "challenge-v2"])

    assert len(digest) == 64
    assert len(challenge_digest) == 64
    assert len(cases) >= 20
    assert any(case["category"] == "prompt-injection" for case in cases)
    assert any(case["category"] == "refusal" for case in cases)
    assert any(case["category"] == "robustness" for case in cases)
    assert any(case["history"] for case in cases)


def test_heldout_lock_fails_closed_after_mutation(tmp_path: Path) -> None:
    heldout = EVALUATION_ROOT / "heldout.json"
    lock = EVALUATION_ROOT / "heldout.sha256"
    (tmp_path / "heldout.json").write_bytes(heldout.read_bytes() + b"\n")
    (tmp_path / "heldout.sha256").write_bytes(lock.read_bytes())

    with pytest.raises(EvaluationDataError, match="heldout.json changed"):
        verify_heldout_lock(tmp_path)


def test_challenge_lock_fails_closed_after_mutation(tmp_path: Path) -> None:
    challenge = EVALUATION_ROOT / "challenge-v2.json"
    lock = EVALUATION_ROOT / "challenge-v2.sha256"
    (tmp_path / challenge.name).write_bytes(challenge.read_bytes() + b"\n")
    (tmp_path / lock.name).write_bytes(lock.read_bytes())

    with pytest.raises(EvaluationDataError, match="challenge-v2.json changed"):
        verify_split_lock("challenge-v2", tmp_path)


def test_challenge_has_balanced_robustness_axes_and_freeze_metadata() -> None:
    payload = json.loads((EVALUATION_ROOT / "challenge-v2.json").read_text())
    cases = load_cases(["challenge-v2"])
    answerable = [case for case in cases if not case["answer_expectation"]["refusal"]]
    refusals = [case for case in cases if case["answer_expectation"]["refusal"]]

    assert payload["protocol"]["candidateFrozenBeforeAuthorship"] is True
    assert len(answerable) == 18
    assert len(refusals) == 4
    assert {case["category"] for case in cases} >= {
        "paraphrase",
        "compositional",
        "follow-up",
        "noisy-query",
        "privacy-boundary",
        "refusal",
        "prompt-injection",
    }
    assert all(case.get("evaluation_axis") for case in cases)
    assert all(isinstance(case.get("fact_ids"), list) for case in cases)
    assert all(case["fact_ids"] for case in answerable)
    assert all(not case["fact_ids"] for case in refusals)
    assert len({case["question"].casefold() for case in cases}) == len(cases)


def test_every_factual_qrel_matches_the_current_deterministic_corpus(pipeline) -> None:
    chunks = [
        {
            "source": chunk.source,
            "chunkIndex": chunk.index,
            "content": chunk.content,
        }
        for document in discover_documents(Path("corpus"))
        for chunk in chunk_document(document, pipeline)
    ]

    for case in load_cases(["dev", "heldout", "challenge-v2", "challenge-v3"]):
        ranks = evidence_group_ranks(case["required_evidence"], chunks)
        assert all(rank is not None for rank in ranks), json.dumps(
            {"case": case["id"], "ranks": ranks}
        )


@pytest.mark.parametrize("split", ["dev", "heldout", "challenge-v2"])
@pytest.mark.parametrize("honor_manual", [False, True])
def test_qrels_remap_to_each_chunking_mode(pipeline, split: str, honor_manual: bool) -> None:
    chunks = [
        {
            "source": chunk.source,
            "chunkIndex": chunk.index,
            "content": chunk.content,
        }
        for document in discover_documents(Path("corpus"))
        for chunk in chunk_document(document, pipeline, honor_manual=honor_manual)
    ]
    cases = load_cases([split])

    remap_cases_to_chunks(cases, chunks)

    for case in cases:
        for group in case["required_evidence"]:
            for option in group["any_of"]:
                matches = [
                    chunk["chunkIndex"]
                    for chunk in chunks
                    if chunk["source"] == option["source"]
                    and any(
                        regex_matches(pattern, chunk["content"])
                        for pattern in option["content_any_of"]
                    )
                ]
                assert option["chunk_indexes"] == sorted(matches)
