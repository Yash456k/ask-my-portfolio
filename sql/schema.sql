CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id bigserial PRIMARY KEY,
    source text NOT NULL UNIQUE,
    title text NOT NULL,
    content_hash text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id bigserial PRIMARY KEY,
    document_id bigint NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source text NOT NULL,
    title text NOT NULL,
    chunk_index integer NOT NULL,
    content text NOT NULL,
    embedding_minilm vector(384),
    embedding_bge_small vector(384),
    embedding_bge_base vector(768),
    embedding_qwen3 vector(1024),
    embedding_portfolio_e5 vector(384),
    embedding_portfolio_gte vector(384),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(document_id, chunk_index)
);

-- CREATE TABLE IF NOT EXISTS does not add columns to an existing deployment.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding_portfolio_e5 vector(384);
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding_portfolio_gte vector(384);

-- The portfolio corpus is deliberately small. Exact scans avoid HNSW graphs,
-- provide perfect recall, and use less resident memory. Add indexes only after
-- measuring a materially larger corpus.

CREATE TABLE IF NOT EXISTS rate_limit_buckets (
    bucket_date date NOT NULL,
    scope text NOT NULL CHECK (scope IN ('ip', 'global')),
    key_hash text NOT NULL,
    request_count integer NOT NULL DEFAULT 0 CHECK (request_count >= 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (bucket_date, scope, key_hash)
);

CREATE TABLE IF NOT EXISTS monthly_budget_buckets (
    bucket_month date PRIMARY KEY,
    reserved_micro_usd bigint NOT NULL DEFAULT 0 CHECK (reserved_micro_usd >= 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (date_trunc('month', bucket_month)::date = bucket_month)
);

CREATE TABLE IF NOT EXISTS query_logs (
    id uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    ip_hash text NOT NULL,
    question text NOT NULL,
    requested_embedder text NOT NULL,
    requested_model text NOT NULL,
    actual_model text,
    fallback_used boolean NOT NULL DEFAULT false,
    fallback_attempts jsonb NOT NULL DEFAULT '[]'::jsonb,
    retrieved_chunks jsonb NOT NULL DEFAULT '[]'::jsonb,
    latencies jsonb NOT NULL DEFAULT '{}'::jsonb,
    answer_characters integer,
    status text NOT NULL DEFAULT 'started',
    error_type text
);

CREATE INDEX IF NOT EXISTS query_logs_created_at_idx ON query_logs (created_at DESC);

ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS answer text;
ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS history jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS top_k integer;
ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS use_history boolean;
ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS visitor_id text;
ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS session_id text;
ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS device_hash text;
ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS user_agent text;
ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS country text;
ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS client jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS retrieval jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS signals jsonb;
CREATE INDEX IF NOT EXISTS query_logs_visitor_idx ON query_logs (visitor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS rate_limit_updated_at_idx ON rate_limit_buckets (updated_at);
CREATE INDEX IF NOT EXISTS monthly_budget_updated_at_idx ON monthly_budget_buckets (updated_at);
