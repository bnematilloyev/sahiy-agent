package postgres

import (
	"context"
	"log/slog"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/feedback"
)

// FeedbackRepository persists star ratings and per-turn telemetry.
// It implements feedback.Recorder.
type FeedbackRepository struct {
	pool *pgxpool.Pool
	log  *slog.Logger
}

// NewFeedbackRepository constructs the repository.
func NewFeedbackRepository(pool *pgxpool.Pool, log *slog.Logger) *FeedbackRepository {
	return &FeedbackRepository{pool: pool, log: log}
}

// RecordRating stores a customer's star rating. A failure is logged and
// dropped: losing one rating must never surface to the customer, who has
// already been thanked for it.
func (r *FeedbackRepository) RecordRating(ctx context.Context, rating feedback.Rating) {
	_, err := r.pool.Exec(ctx, `
		INSERT INTO agent_ratings (user_id, channel, session_id, stars)
		VALUES ($1, $2, $3, $4)`,
		rating.UserID, rating.Channel, nullableUUID(rating.SessionID), rating.Stars,
	)
	if err != nil {
		r.log.Error("feedback: rating insert failed", "error", err, "user_id", rating.UserID)
	}
}

// RecordTurn stores one answered message's quality telemetry.
func (r *FeedbackRepository) RecordTurn(ctx context.Context, t feedback.Turn) {
	_, err := r.pool.Exec(ctx, `
		INSERT INTO agent_turns
			(session_id, channel, route, reply_language, confidence,
			 escalated, handoff_reason, degraded, duration_ms)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`,
		nullableUUID(t.SessionID), t.Channel, t.Route, t.ReplyLanguage, t.Confidence,
		t.Escalated, t.HandoffReason, t.Degraded, t.Duration.Milliseconds(),
	)
	if err != nil {
		r.log.Error("feedback: turn insert failed", "error", err, "route", t.Route)
	}
}

// nullableUUID renders an empty session id as SQL NULL rather than letting the
// driver try to parse "" as a UUID.
func nullableUUID(id string) any {
	if id == "" {
		return nil
	}
	return id
}
