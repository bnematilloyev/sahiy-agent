-- The learning loop: what the assistant did, and what customers thought of it.
--
-- Like agent_token_usage these are append-only telemetry tables written from
-- detached goroutines, so they carry no FOREIGN KEY to chat_sessions: a write
-- must never fail, and the record stays true after its session is deleted.
-- session_id NULL means the row could not be attributed to a session.

-- One row per customer star rating.
CREATE TABLE IF NOT EXISTS agent_ratings (
    id         BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    user_id    VARCHAR(255) NOT NULL,
    channel    VARCHAR(50)  NOT NULL DEFAULT '',
    session_id UUID,
    stars      SMALLINT     NOT NULL CHECK (stars BETWEEN 1 AND 5)
);
CREATE INDEX IF NOT EXISTS ix_agent_ratings_created_at ON agent_ratings (created_at);
CREATE INDEX IF NOT EXISTS ix_agent_ratings_session_id ON agent_ratings (session_id);

-- One row per answered message: which route handled it, how sure the assistant
-- was, and whether it had to hand off. Joined against agent_ratings this is
-- what makes "which routes get bad ratings" answerable; joined against
-- agent_token_usage it gives cost per route.
CREATE TABLE IF NOT EXISTS agent_turns (
    id             BIGSERIAL PRIMARY KEY,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id     UUID,
    channel        VARCHAR(50) NOT NULL DEFAULT '',
    route          VARCHAR(50) NOT NULL DEFAULT '',
    reply_language VARCHAR(10) NOT NULL DEFAULT '',
    confidence     REAL        NOT NULL DEFAULT 0,
    escalated      BOOLEAN     NOT NULL DEFAULT false,
    handoff_reason VARCHAR(50) NOT NULL DEFAULT '',
    -- degraded means no real model answered: the reply came from the rules
    -- fallback. A run of these is an outage, not a quality problem.
    degraded    BOOLEAN NOT NULL DEFAULT false,
    duration_ms INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_agent_turns_created_at ON agent_turns (created_at);
CREATE INDEX IF NOT EXISTS ix_agent_turns_session_id ON agent_turns (session_id);
CREATE INDEX IF NOT EXISTS ix_agent_turns_route ON agent_turns (route);
