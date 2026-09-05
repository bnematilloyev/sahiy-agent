package postgres

import (
	"context"
	"log/slog"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
)

// TokenUsageRepository persists raw per-call token counts to agent_token_usage.
// It implements ai.UsageRecorder.
type TokenUsageRepository struct {
	pool *pgxpool.Pool
	log  *slog.Logger
}

// NewTokenUsageRepository constructs the repository.
func NewTokenUsageRepository(pool *pgxpool.Pool, log *slog.Logger) *TokenUsageRepository {
	return &TokenUsageRepository{pool: pool, log: log}
}

// RecordUsage inserts one row. The caller (llm.ChainedClient) already runs this
// off a detached, timeout-bounded context, so a failure here is logged and
// dropped rather than surfaced - losing one usage row must never affect a
// customer-facing reply.
func (r *TokenUsageRepository) RecordUsage(ctx context.Context, rec ai.UsageRecord) {
	_, err := r.pool.Exec(ctx, `
		INSERT INTO agent_token_usage
			(provider, model, route, session_id, input_tokens, output_tokens,
			 cache_read_input_tokens, cache_creation_input_tokens)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
		rec.Provider, rec.Model, rec.Route, nullableUUID(rec.SessionID),
		rec.Usage.InputTokens, rec.Usage.OutputTokens,
		rec.Usage.CacheReadInputTokens, rec.Usage.CacheCreationInputTokens,
	)
	if err != nil {
		r.log.Error("token usage: insert failed", "error", err, "provider", rec.Provider, "route", rec.Route)
	}
}
