-- Initial schema for sahiy-agent (Go).
-- Written idempotently so it coexists with an existing Alembic-created schema.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chat_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     VARCHAR(255) NOT NULL,
    channel     VARCHAR(50)  NOT NULL DEFAULT 'telegram',
    status      VARCHAR(20)  NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_chat_sessions_user_id ON chat_sessions (user_id);

CREATE TABLE IF NOT EXISTS messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL REFERENCES chat_sessions (id) ON DELETE CASCADE,
    role        VARCHAR(20) NOT NULL,
    content     TEXT        NOT NULL,
    msg_type    VARCHAR(20),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_messages_session_id ON messages (session_id);

CREATE TABLE IF NOT EXISTS faq_embeddings (
    id          SERIAL PRIMARY KEY,
    question    TEXT NOT NULL,
    answer      TEXT NOT NULL,
    category    VARCHAR(100) NOT NULL DEFAULT 'general',
    question_uz  TEXT,
    answer_uz    TEXT,
    question_cyr TEXT,
    answer_cyr   TEXT,
    question_ru  TEXT,
    answer_ru    TEXT,
    question_en  TEXT,
    answer_en    TEXT,
    question_zh  TEXT,
    answer_zh    TEXT,
    embedding   vector(1536)
);
CREATE INDEX IF NOT EXISTS ix_faq_embeddings_embedding
    ON faq_embeddings USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS tickets (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL REFERENCES chat_sessions (id) ON DELETE CASCADE,
    user_id     VARCHAR(255) NOT NULL,
    type        VARCHAR(50)  NOT NULL,
    status      VARCHAR(20)  NOT NULL DEFAULT 'open',
    operator_id VARCHAR(255),
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_tickets_session_id ON tickets (session_id);
CREATE INDEX IF NOT EXISTS ix_tickets_user_id ON tickets (user_id);
