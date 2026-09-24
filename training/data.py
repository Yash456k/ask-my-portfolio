from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import ChunkingConfig, load_pipeline
from app.ingest import chunk_document, discover_documents

TRAIN_MINIMUM_EXAMPLES = 60


@dataclass(frozen=True)
class DatasetBundle:
    chunks: dict[str, str]
    train: list[dict[str, Any]]
    dev: list[dict[str, Any]]
    locked_holdout: list[dict[str, Any]]
    hashes: dict[str, str]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            value = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: each line must be a JSON object")
        records.append(value)
    if not records:
        raise ValueError(f"{path}: dataset is empty")
    return records


# The corpus exactly as the training data was reviewed against it (git f16acb2). Training
# stays pinned to this copy, so editing the live corpus/ neither breaks nor silently
# redefines the passages the existing fine-tunes learned. Retraining on newer content means
# refreshing this snapshot and corpus-lock.json, then re-reviewing every example.
TRAINING_CORPUS = Path("training") / "data" / "corpus-snapshot"


def build_chunk_snapshot(
    repo_root: Path, locked_chunking: dict[str, Any] | None = None
) -> dict[str, str]:
    corpus_path = repo_root / TRAINING_CORPUS
    pipeline = load_pipeline(repo_root / "config" / "pipeline.yaml")
    if locked_chunking is not None:
        pipeline = pipeline.model_copy(
            update={"chunking": ChunkingConfig.model_validate(locked_chunking)}
        )
    chunks: dict[str, str] = {}
    for document in discover_documents(corpus_path):
        # Training artifacts remain locked to the reviewed automatic snapshot. Manual
        # production boundaries may change retrieval without silently redefining the
        # passages that the existing fine-tunes were trained against.
        for chunk in chunk_document(document, pipeline, honor_manual=False):
            chunk_id = f"{chunk.source}#{chunk.index}"
            if chunk_id in chunks:
                raise ValueError(f"duplicate corpus chunk id: {chunk_id}")
            chunks[chunk_id] = chunk.content
    if not chunks:
        raise ValueError("the current corpus produced no chunks")
    return chunks


def _normalized_question(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip().rstrip("?.!")


def _validate_id_and_question(
    record: dict[str, Any],
    *,
    split: str,
    record_ids: set[str],
    questions: dict[str, str],
) -> None:
    record_id = record.get("id")
    question = record.get("question")
    if not isinstance(record_id, str) or not record_id.strip():
        raise ValueError(f"{split}: every record needs a non-empty string id")
    if record_id in record_ids:
        raise ValueError(f"duplicate dataset id: {record_id}")
    record_ids.add(record_id)
    if not isinstance(question, str) or len(question.split()) < 4:
        raise ValueError(f"{record_id}: question must contain at least four words")
    normalized = _normalized_question(question)
    if normalized in questions:
        raise ValueError(
            f"question leakage between {questions[normalized]} and {record_id}: {question!r}"
        )
    questions[normalized] = record_id


def validate_datasets(
    *,
    chunks: dict[str, str],
    train: list[dict[str, Any]],
    dev: list[dict[str, Any]],
    locked_holdout: list[dict[str, Any]],
) -> None:
    if len(train) < TRAIN_MINIMUM_EXAMPLES:
        raise ValueError(
            f"train set has {len(train)} examples; need at least {TRAIN_MINIMUM_EXAMPLES}"
        )

    record_ids: set[str] = set()
    questions: dict[str, str] = {}
    covered_chunks: set[str] = set()
    for record in train:
        _validate_id_and_question(
            record,
            split="train",
            record_ids=record_ids,
            questions=questions,
        )
        expected = {"id", "question", "positive_chunk_id", "hard_negative_chunk_id"}
        if set(record) != expected:
            raise ValueError(f"{record['id']}: expected fields {sorted(expected)}")
        positive = record["positive_chunk_id"]
        negative = record["hard_negative_chunk_id"]
        if positive not in chunks or negative not in chunks:
            raise ValueError(f"{record['id']}: references an unknown corpus chunk")
        if positive == negative:
            raise ValueError(f"{record['id']}: positive and hard negative must differ")
        covered_chunks.add(positive)

    missing_chunks = sorted(set(chunks) - covered_chunks)
    if missing_chunks:
        raise ValueError(f"train examples do not cover corpus chunks: {missing_chunks}")

    for split, records in (("dev", dev), ("locked_holdout", locked_holdout)):
        for record in records:
            _validate_id_and_question(
                record,
                split=split,
                record_ids=record_ids,
                questions=questions,
            )
            expected = {"id", "question", "relevant_chunk_ids"}
            if set(record) != expected:
                raise ValueError(f"{record['id']}: expected fields {sorted(expected)}")
            relevant = record["relevant_chunk_ids"]
            if not isinstance(relevant, list) or not relevant:
                raise ValueError(f"{record['id']}: relevant_chunk_ids must be a non-empty list")
            if len(relevant) != len(set(relevant)) or any(item not in chunks for item in relevant):
                raise ValueError(f"{record['id']}: relevant_chunk_ids are invalid")


def load_and_validate(repo_root: Path) -> DatasetBundle:
    data_dir = repo_root / "training" / "data"
    paths = {
        "train": data_dir / "train.jsonl",
        "dev": data_dir / "dev.jsonl",
        "locked_holdout": data_dir / "locked_holdout.jsonl",
    }
    lock_path = data_dir / "corpus-lock.json"
    corpus_lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if corpus_lock.get("schema_version") != 2:
        raise ValueError("training/data/corpus-lock.json has an unsupported schema version")
    chunks = build_chunk_snapshot(repo_root, corpus_lock.get("chunking"))
    chunk_hash = _canonical_hash(chunks)
    if corpus_lock.get("corpus_chunks_sha256") != chunk_hash:
        raise ValueError(
            "corpus chunks changed after dataset review; refresh corpus-lock.json and manually "
            "re-review every positive and hard negative before training"
        )
    if sorted(corpus_lock.get("chunk_ids", [])) != sorted(chunks):
        raise ValueError("corpus-lock.json chunk ids do not match the current ingestion chunks")
    review = corpus_lock.get("hard_negative_review")
    if not isinstance(review, dict) or review.get("status") != "reviewed":
        raise ValueError("hard negatives must be manually reviewed against the locked corpus")
    expected_source_hashes = corpus_lock.get("source_file_sha256", {})
    actual_source_hashes = {
        f"corpus/{path.name}": sha256_file(path)
        for path in sorted((repo_root / TRAINING_CORPUS).glob("*"))
        if path.is_file()
    }
    if expected_source_hashes != actual_source_hashes:
        raise ValueError("corpus source hashes do not match corpus-lock.json")
    train = _read_jsonl(paths["train"])
    dev = _read_jsonl(paths["dev"])
    locked_holdout = _read_jsonl(paths["locked_holdout"])
    validate_datasets(
        chunks=chunks,
        train=train,
        dev=dev,
        locked_holdout=locked_holdout,
    )
    hashes = {f"{name}_file_sha256": sha256_file(path) for name, path in paths.items()}
    hashes.update(
        {
            "corpus_lock_file_sha256": sha256_file(lock_path),
            "train_semantic_sha256": _canonical_hash(train),
            "dev_semantic_sha256": _canonical_hash(dev),
            "locked_holdout_semantic_sha256": _canonical_hash(locked_holdout),
            "corpus_chunks_sha256": chunk_hash,
        }
    )
    return DatasetBundle(
        chunks=chunks,
        train=train,
        dev=dev,
        locked_holdout=locked_holdout,
        hashes=hashes,
    )
