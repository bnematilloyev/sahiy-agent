-- Raw per-call token accounting from the LLM provider's own usage response
-- (not estimated). Cost is deliberately NOT computed or stored here: per-token
-- pricing differs by token kind (input / output / cache write / cache read)
-- and by model, and those rates change independently of this data - compute
-- cost at query time from the raw counts instead of baking a snapshot of
-- today's pricing into historical rows.
CREATE TABLE IF NOT EXISTS agent_token_usage (
    id                           BIGSERIAL PRIMARY KEY,
    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    provider                     VARCHAR(50) NOT NULL,
    model                        VARCHAR(100) NOT NULL DEFAULT '',
    route                        VARCHAR(50) NOT NULL DEFAULT '',
    input_tokens                 INTEGER NOT NULL DEFAULT 0,
    output_tokens                INTEGER NOT NULL DEFAULT 0,
    cache_read_input_tokens      INTEGER NOT NULL DEFAULT 0,
    cache_creation_input_tokens  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_agent_token_usage_created_at ON agent_token_usage (created_at);
CREATE INDEX IF NOT EXISTS ix_agent_token_usage_route ON agent_token_usage (route);
