-- Attribute each LLM call to the chat session it served, so an unexpected
-- token spend can be traced back to the conversation that caused it.
--
-- Deliberately no FOREIGN KEY to chat_sessions: this is an append-only
-- telemetry table written from a detached background goroutine that must never
-- fail a write, and the token spend remains a true historical fact even after
-- its session row is deleted. Joins for debugging still work:
--   SELECT u.* FROM agent_token_usage u JOIN chat_sessions s ON s.id = u.session_id
-- NULL means the call was made outside any chat session.
ALTER TABLE agent_token_usage ADD COLUMN IF NOT EXISTS session_id UUID;
CREATE INDEX IF NOT EXISTS ix_agent_token_usage_session_id ON agent_token_usage (session_id);
