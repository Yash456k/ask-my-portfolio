-- Full question/answer logging for grading, plus pseudonymous visitor context.
-- Idempotent; run as the database owner (the public runtime role cannot alter tables).
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
CREATE INDEX IF NOT EXISTS query_logs_visitor_idx ON query_logs (visitor_id, created_at DESC);
