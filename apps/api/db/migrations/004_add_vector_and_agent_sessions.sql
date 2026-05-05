CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE sections ADD COLUMN IF NOT EXISTS embedding vector(768);

CREATE TABLE IF NOT EXISTS agent_sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    history JSON NOT NULL DEFAULT '[]'::json
);

CREATE INDEX IF NOT EXISTS ix_agent_sessions_user_id ON agent_sessions(user_id);
