from __future__ import annotations

from types import SimpleNamespace

from app.config import PipelineConfig
from app.ingest import Chunk, _reusable_vectors, _unchanged, embedder_fingerprint

CHUNKS = [
    Chunk("about.md", "About", 0, "Yash builds software."),
    Chunk("projects.md", "Projects", 0, "Ask my portfolio answers questions."),
]


def _connection(rows: list[tuple]) -> SimpleNamespace:
    return SimpleNamespace(execute=lambda query: SimpleNamespace(fetchall=lambda: rows))


def _rows(chunks: list[Chunk], filled: bool = True) -> list[tuple]:
    # Stored order is arbitrary; the comparison must not depend on it.
    return [(c.source, c.index, c.title, c.content, filled) for c in reversed(chunks)]


def test_unchanged_corpus_with_every_vector_is_skipped(pipeline: PipelineConfig) -> None:
    assert _unchanged(_connection(_rows(CHUNKS)), CHUNKS, pipeline)


def test_edited_added_or_removed_chunks_are_ingested(pipeline: PipelineConfig) -> None:
    edited = [CHUNKS[0], Chunk("projects.md", "Projects", 0, "Now with a new sentence.")]
    assert not _unchanged(_connection(_rows(CHUNKS)), edited, pipeline)
    assert not _unchanged(_connection(_rows(CHUNKS[:1])), CHUNKS, pipeline)
    assert not _unchanged(_connection(_rows(CHUNKS)), CHUNKS[:1], pipeline)


def test_missing_vectors_are_ingested(pipeline: PipelineConfig) -> None:
    assert not _unchanged(_connection(_rows(CHUNKS, filled=False)), CHUNKS, pipeline)


def _stored(fingerprint: str | None, rows: list[tuple]) -> SimpleNamespace:
    def execute(query: object) -> SimpleNamespace:
        documents = isinstance(query, str) and "FROM documents" in query
        return SimpleNamespace(fetchall=lambda: [(fingerprint,)] if documents else rows)

    return SimpleNamespace(execute=execute)


def test_stored_vectors_are_reused_only_from_the_same_embedders(pipeline: PipelineConfig) -> None:
    vectors = tuple([0.1, 0.2] for _ in pipeline.embedders)
    rows = [("Yash builds software.", *vectors), ("Half embedded.", None, *vectors[1:])]

    reused = _reusable_vectors(_stored(embedder_fingerprint(pipeline), rows), pipeline)
    assert reused == {"Yash builds software.": vectors}
    # Vectors from other embedders, or from before fingerprints were recorded, are re-embedded.
    assert _reusable_vectors(_stored("another-model-set", rows), pipeline) == {}
    assert _reusable_vectors(_stored(None, rows), pipeline) == {}
