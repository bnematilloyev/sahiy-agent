package postgres

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/conversation"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/support"
)

// TicketRepository is the pgx-backed implementation of support.Repository.
type TicketRepository struct {
	pool *pgxpool.Pool
}

// NewTicketRepository constructs the repository.
func NewTicketRepository(pool *pgxpool.Pool) *TicketRepository {
	return &TicketRepository{pool: pool}
}

func (r *TicketRepository) Save(ctx context.Context, t *support.Ticket) error {
	const q = `
		INSERT INTO tickets (id, session_id, user_id, type, status, operator_id, created_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
		ON CONFLICT (id) DO UPDATE
		SET status = EXCLUDED.status, operator_id = EXCLUDED.operator_id`

	var operator *string
	if op := t.OperatorID(); op != "" {
		operator = &op
	}
	if _, err := r.pool.Exec(ctx, q,
		t.ID().UUID(), t.SessionID().UUID(), t.UserID().String(),
		t.Type().String(), string(t.Status()), operator, t.CreatedAt(),
	); err != nil {
		return fmt.Errorf("ticket: save: %w", err)
	}
	return nil
}

func (r *TicketRepository) FindOpenBySession(ctx context.Context, sessionID conversation.SessionID) (*support.Ticket, error) {
	const q = `
		SELECT id, session_id, user_id, type, status, COALESCE(operator_id, ''), created_at
		FROM tickets
		WHERE session_id = $1 AND status != 'closed'
		ORDER BY created_at DESC
		LIMIT 1`

	var (
		idStr      string
		sessStr    string
		userIDStr  string
		ticketType string
		status     string
		operatorID string
		createdAt  time.Time
	)
	err := r.pool.QueryRow(ctx, q, sessionID.UUID()).
		Scan(&idStr, &sessStr, &userIDStr, &ticketType, &status, &operatorID, &createdAt)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("ticket: find open: %w", err)
	}

	tid := support.TicketIDFromUUID(mustUUID(idStr))
	userID, err := shared.NewUserID(userIDStr)
	if err != nil {
		return nil, fmt.Errorf("ticket: hydrate user id: %w", err)
	}
	sid, _ := conversation.ParseSessionID(sessStr)

	return support.Reconstitute(
		tid, sid, userID, support.NewType(ticketType),
		support.Status(status), operatorID, createdAt,
	), nil
}

func (r *TicketRepository) CloseBySession(ctx context.Context, sessionID conversation.SessionID) error {
	const q = `UPDATE tickets SET status = 'closed' WHERE session_id = $1 AND status != 'closed'`
	if _, err := r.pool.Exec(ctx, q, sessionID.UUID()); err != nil {
		return fmt.Errorf("ticket: close by session: %w", err)
	}
	return nil
}
