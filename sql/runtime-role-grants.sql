-- Run as database owner during deployment, NOT from the public API.
-- Provision rag_runtime's random password outside Git (private .env.runtime).
-- Existing schema is bootstrapped separately using sql/schema.sql.
ALTER ROLE rag_runtime NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 8;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE rag_playground FROM PUBLIC;
GRANT CONNECT ON DATABASE rag_playground TO rag_runtime;
GRANT USAGE ON SCHEMA public TO rag_runtime;
GRANT SELECT ON documents, chunks TO rag_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON rate_limit_buckets, monthly_budget_buckets TO rag_runtime;
-- Question logs are kept for answer grading: the public API may add and complete rows, never delete them.
GRANT SELECT, INSERT, UPDATE ON query_logs TO rag_runtime;
REVOKE DELETE ON query_logs FROM rag_runtime;
ALTER ROLE rag_runtime SET statement_timeout = '15s';
ALTER ROLE rag_runtime SET lock_timeout = '3s';
ALTER ROLE rag_runtime SET idle_in_transaction_session_timeout = '15s';
