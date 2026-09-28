from __future__ import annotations

import argparse
import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql
from pypdf import PdfReader

from app.config import PipelineConfig, load_pipeline
from app.database import content_digest
from app.embeddings import EmbeddingRegistry
from app.settings import get_settings

logger = logging.getLogger(__name__)
SUPPORTED_SUFFIXES = {".md", ".txt", ".pdf"}
MANUAL_CHUNK_MARKER = re.compile(
    r"<!--\s*rag-chunk:\s*"
    r"([a-z0-9](?:[a-z0-9-]*[a-z0-9])?)\s*\|\s*([^<>\r\n]+?)\s*-->"
)
MANUAL_CHUNK_SENTINEL = re.compile(r"<!--\s*rag-chunk:", re.IGNORECASE)
MANUAL_CHUNK_MAXIMUM_MULTIPLIER = 2


@dataclass(frozen=True)
class SourceDocument:
    source: str
    title: str
    content: str


@dataclass(frozen=True)
class Chunk:
    source: str
    title: str
    index: int
    content: str
    semantic_id: str | None = None


def read_source(path: Path, root: Path) -> SourceDocument:
    if path.suffix.lower() == ".pdf":
        pages = [page.extract_text() or "" for page in PdfReader(path).pages]
        content = "\n\n".join(pages)
    else:
        content = path.read_text(encoding="utf-8")
    content = content.replace("\r\n", "\n").strip()
    heading = next(
        (line.lstrip("# ").strip() for line in content.splitlines() if line.startswith("#")),
        path.stem.replace("-", " ").title(),
    )
    return SourceDocument(
        source=path.relative_to(root).as_posix(),
        title=heading,
        content=content,
    )


def discover_documents(root: Path) -> list[SourceDocument]:
    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
    if not paths:
        raise RuntimeError(f"No supported corpus documents found in {root}")
    documents = [read_source(path, root) for path in paths]
    empty = [document.source for document in documents if not document.content]
    if empty:
        raise RuntimeError(f"Empty corpus documents: {', '.join(empty)}")
    return documents


def _split_oversized(text: str, maximum: int) -> list[str]:
    words = text.split()
    sections: list[str] = []
    current: list[str] = []
    length = 0
    for word in words:
        if len(word) > maximum:
            if current:
                sections.append(" ".join(current))
                current = []
                length = 0
            sections.extend(word[index : index + maximum] for index in range(0, len(word), maximum))
            continue
        extra = len(word) + (1 if current else 0)
        if current and length + extra > maximum:
            sections.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += extra
    if current:
        sections.append(" ".join(current))
    return sections


def _word_aligned_suffix(text: str, maximum: int) -> str:
    """Return at most ``maximum`` trailing characters without starting mid-token."""
    if maximum <= 0:
        return ""
    start = max(0, len(text) - maximum)
    if start == 0:
        return text
    if text[start - 1].isspace() or text[start].isspace():
        return text[start:].lstrip()
    boundary = re.search(r"\s+", text[start:])
    if boundary is None:
        return ""
    return text[start + boundary.end() :].lstrip()


def _strip_manual_chunk_markers(content: str) -> str:
    def replacement(match: re.Match[str]) -> str:
        before = content[match.start() - 1 : match.start()]
        after = content[match.end() : match.end() + 1]
        if before and after and not before.isspace() and not after.isspace():
            return " "
        return ""

    return MANUAL_CHUNK_MARKER.sub(replacement, content)


def _manual_chunks(document: SourceDocument, pipeline: PipelineConfig) -> list[Chunk] | None:
    matches = list(MANUAL_CHUNK_MARKER.finditer(document.content))
    marker_count = len(MANUAL_CHUNK_SENTINEL.findall(document.content))
    if marker_count != len(matches):
        raise RuntimeError(
            f"Malformed manual chunk marker in {document.source}; expected "
            "<!-- rag-chunk: stable-id | semantic topic -->"
        )
    if not matches:
        return None
    if document.content[: matches[0].start()].strip():
        raise RuntimeError(f"{document.source}: content appears before the first manual chunk")

    seen: set[str] = set()
    chunks: list[Chunk] = []
    maximum = pipeline.chunking.max_characters * MANUAL_CHUNK_MAXIMUM_MULTIPLIER
    for index, match in enumerate(matches):
        semantic_id = match.group(1)
        if semantic_id in seen:
            raise RuntimeError(f"{document.source}: duplicate manual chunk id {semantic_id!r}")
        seen.add(semantic_id)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(document.content)
        body = document.content[match.end() : end].strip()
        if not body:
            raise RuntimeError(f"{document.source}: manual chunk {semantic_id!r} is empty")
        topic = re.sub(r"\s+", " ", match.group(2)).strip()
        content = f"Topic: {topic}\n\n{body}"
        if len(content) > maximum:
            raise RuntimeError(
                f"{document.source}: manual chunk {semantic_id!r} has {len(content)} characters; "
                f"maximum is {maximum}"
            )
        chunks.append(
            Chunk(document.source, document.title, index, content, semantic_id=semantic_id)
        )
    return chunks


def chunk_document(
    document: SourceDocument,
    pipeline: PipelineConfig,
    *,
    honor_manual: bool = True,
) -> list[Chunk]:
    config = pipeline.chunking
    if honor_manual:
        manual = _manual_chunks(document, pipeline)
        if manual is not None:
            return manual
    content = _strip_manual_chunk_markers(document.content)
    raw_sections = [
        re.sub(r"\s+", " ", section).strip()
        for section in re.split(r"\n\s*\n", content)
        if section.strip()
    ]
    sections: list[str] = []
    for section in raw_sections:
        if len(section) > config.max_characters:
            sections.extend(_split_oversized(section, config.max_characters))
        else:
            sections.append(section)

    texts: list[str] = []
    current = ""
    for section in sections:
        candidate = f"{current}\n\n{section}".strip() if current else section
        if current and len(candidate) > config.max_characters:
            texts.append(current)
            available_overlap = max(0, config.max_characters - len(section) - 2)
            overlap_length = min(config.overlap_characters, available_overlap)
            overlap = _word_aligned_suffix(current, overlap_length)
            current = f"{overlap}\n\n{section}".strip() if overlap else section
        else:
            current = candidate
    if current:
        merged_length = len(texts[-1]) + 2 + len(current) if texts else 0
        if (
            texts
            and len(current) < config.minimum_characters
            and merged_length <= config.max_characters
        ):
            texts[-1] = f"{texts[-1]}\n\n{current}"
        else:
            texts.append(current)

    return [Chunk(document.source, document.title, index, text) for index, text in enumerate(texts)]


async def load_registry(pipeline: PipelineConfig) -> EmbeddingRegistry:
    registry = EmbeddingRegistry(pipeline)
    await registry.load_all()
    return registry


def _unchanged(
    connection: psycopg.Connection, chunks: list[Chunk], pipeline: PipelineConfig
) -> bool:
    """True when the stored chunks match the corpus and every vector column is filled."""
    filled = sql.SQL(" AND ").join(
        sql.SQL("{} IS NOT NULL").format(sql.Identifier(config.column))
        for config in pipeline.embedders
    )
    rows = connection.execute(
        sql.SQL("SELECT source, chunk_index, title, content, {} FROM chunks").format(filled)
    ).fetchall()
    stored = sorted((source, index, title, content) for source, index, title, content, _ in rows)
    wanted = sorted((chunk.source, chunk.index, chunk.title, chunk.content) for chunk in chunks)
    return stored == wanted and all(row[4] for row in rows)


def ingest(corpus_path: Path, *, reason: str = "re-ingest", force: bool = False) -> None:
    settings = get_settings()
    pipeline = load_pipeline()
    documents = discover_documents(corpus_path)
    chunks = [chunk for document in documents for chunk in chunk_document(document, pipeline)]
    logger.info("Prepared %d chunks from %d documents", len(chunks), len(documents))

    schema = (Path(__file__).parents[1] / "sql" / "schema.sql").read_text(encoding="utf-8")
    with psycopg.connect(settings.database_url) as connection:
        # The live API may be serving; fail fast instead of queueing its queries behind DDL locks.
        connection.execute("SET lock_timeout = '5s'")
        connection.execute(schema)
        connection.commit()
        register_vector(connection)
        if not force and _unchanged(connection, chunks, pipeline):
            logger.info("Corpus unchanged and every vector column is filled; nothing to ingest")
            return
        connection.commit()

        registry = asyncio.run(load_registry(pipeline))
        texts = [chunk.content for chunk in chunks]
        vectors = {
            config.id: registry.encode_documents(config.id, texts).tolist()
            for config in pipeline.embedders
        }

        # One transaction: the API reads the old corpus until commit, then the new one.
        with connection.transaction():
            # Query logs cite chunk ids, which this swap replaces; keep the old text for grading.
            connection.execute(
                "INSERT INTO chunk_history (chunk_id, source, chunk_index, content, reason) "
                "SELECT id, source, chunk_index, content, %s FROM chunks",
                (reason,),
            )
            connection.execute("DELETE FROM chunks")
            connection.execute("DELETE FROM documents")
            document_ids: dict[str, int] = {}
            for document in documents:
                row = connection.execute(
                    """
                    INSERT INTO documents (source, title, content_hash, metadata)
                    VALUES (%s, %s, %s, %s::jsonb)
                    RETURNING id
                    """,
                    (document.source, document.title, content_digest(document.content), "{}"),
                ).fetchone()
                if row is None:
                    raise RuntimeError(f"Failed to insert {document.source}")
                document_ids[document.source] = int(row[0])

            rows = []
            for index, chunk in enumerate(chunks):
                rows.append(
                    (
                        document_ids[chunk.source],
                        chunk.source,
                        chunk.title,
                        chunk.index,
                        chunk.content,
                        *(vectors[config.id][index] for config in pipeline.embedders),
                    )
                )
            insert_columns = [
                "document_id",
                "source",
                "title",
                "chunk_index",
                "content",
                *(config.column for config in pipeline.embedders),
            ]
            insert_query = sql.SQL("INSERT INTO chunks ({columns}) VALUES ({values})").format(
                columns=sql.SQL(", ").join(map(sql.Identifier, insert_columns)),
                values=sql.SQL(", ").join(sql.Placeholder() for _ in insert_columns),
            )
            with connection.cursor() as cursor:
                cursor.executemany(insert_query, rows)
    logger.info(
        "Ingestion complete: %d documents / %d chunks / %d vector spaces",
        len(documents),
        len(chunks),
        len(pipeline.embedders),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest portfolio documents into all vector spaces"
    )
    parser.add_argument("--corpus", type=Path, default=Path("corpus"))
    parser.add_argument(
        "--reason", default="re-ingest", help="Recorded with the replaced chunks in chunk_history"
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-embed even when the corpus is unchanged"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ingest(args.corpus.resolve(), reason=args.reason, force=args.force)


if __name__ == "__main__":
    main()
