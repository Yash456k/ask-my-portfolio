-- Answer grading and blind model comparison. Run as the database owner after creating the
-- rag_grader role with a random password kept outside Git (deployment step).
CREATE TABLE IF NOT EXISTS answer_grades (
    query_log_id uuid PRIMARY KEY REFERENCES query_logs(id) ON DELETE CASCADE,
    grade text NOT NULL CHECK (grade IN ('good', 'ok', 'bad')),
    note text NOT NULL DEFAULT '' CHECK (length(note) <= 2000),
    graded_by text,
    graded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS model_pairs (
    id bigserial PRIMARY KEY,
    run text NOT NULL,
    case_id text NOT NULL,
    question text NOT NULL,
    history jsonb NOT NULL DEFAULT '[]'::jsonb,
    answer_a text NOT NULL,
    answer_b text NOT NULL,
    model_a text NOT NULL,
    model_b text NOT NULL,
    choice text CHECK (choice IN ('a', 'b', 'tie', 'both_bad')),
    note text NOT NULL DEFAULT '' CHECK (length(note) <= 2000),
    decided_by text,
    decided_at timestamptz,
    UNIQUE (run, case_id)
);

-- The grader reads logs and chunk text and writes only grades and pair choices.
ALTER ROLE rag_grader NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 4;
ALTER ROLE rag_grader SET statement_timeout = '10s';
GRANT CONNECT ON DATABASE rag_playground TO rag_grader;
GRANT USAGE ON SCHEMA public TO rag_grader;
GRANT SELECT ON query_logs, chunks, chunk_history TO rag_grader;
GRANT SELECT, INSERT, UPDATE ON answer_grades TO rag_grader;
GRANT SELECT ON model_pairs TO rag_grader;
GRANT UPDATE (choice, note, decided_by, decided_at) ON model_pairs TO rag_grader;
