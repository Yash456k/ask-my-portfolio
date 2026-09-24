-- Jev conversation signals (intent, tone, chat mood, coverage) for each question.
ALTER TABLE query_logs ADD COLUMN IF NOT EXISTS signals jsonb;
