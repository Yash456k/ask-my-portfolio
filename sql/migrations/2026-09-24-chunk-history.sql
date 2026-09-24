-- Chunk text as it was before each re-ingestion. Query logs reference chunks by id, and
-- re-ingestion replaces ids, so graded answers join here to recover the exact evidence.
-- Owner-only: the public runtime role has no grant on this table.
CREATE TABLE IF NOT EXISTS chunk_history (
    chunk_id bigint NOT NULL,
    source text NOT NULL,
    chunk_index integer NOT NULL,
    content text NOT NULL,
    archived_at timestamptz NOT NULL DEFAULT now(),
    reason text NOT NULL,
    PRIMARY KEY (chunk_id, archived_at)
);
