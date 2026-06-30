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
)

// defaultHistoryWindow is how many recent messages are hydrated into a session
// aggregate. It is enough context for routing without loading entire histories.
const defaultHistoryWindow = 20

// ConversationRepository is the pgx-backed implementation of
// conversation.Repository.
type ConversationRepository struct {
	pool          *pgxpool.Pool
	historyWindow int
}

// NewConversationRepository constructs the repository.
func NewConversationRepository(pool *pgxpool.Pool) *ConversationRepository {
	return &ConversationRepository{pool: pool, historyWindow: defaultHistoryWindow}
}

func (r *ConversationRepository) FindByID(ctx context.Context, id conversation.SessionID) (*conversation.Session, error) {
	const q = `SELECT id, user_id, channel, status, created_at FROM chat_sessions WHERE id = $1`
	return r.hydrate(ctx, r.pool.QueryRow(ctx, q, id.UUID()))
}

func (r *ConversationRepository) FindActive(ctx context.Context, userID shared.UserID, channel conversation.Channel) (*conversation.Session, error) {
	const q = `
		SELECT id, user_id, channel, status, created_at
		FROM chat_sessions
		WHERE user_id = $1 AND channel = $2 AND status = 'active'
		ORDER BY created_at DESC
		LIMIT 1`
	return r.hydrate(ctx, r.pool.QueryRow(ctx, q, userID.String(), channel.String()))
}

// hydrate scans a session row and loads its recent message window.
func (r *ConversationRepository) hydrate(ctx context.Context, scanRow pgx.Row) (*conversation.Session, error) {
	var (
		idStr     string
		userIDStr string
		channel   string
		status    string
		createdAt time.Time
	)
	if err := scanRow.Scan(&idStr, &userIDStr, &channel, &status, &createdAt); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, nil
		}
		return nil, fmt.Errorf("conversation: scan session: %w", err)
	}

	id, _ := conversation.ParseSessionID(idStr)
	userID, err := shared.NewUserID(userIDStr)
	if err != nil {
		return nil, fmt.Errorf("conversation: hydrate user id: %w", err)
	}

	messages, err := r.loadMessages(ctx, id)
	if err != nil {
		return nil, err
	}

	return conversation.Reconstitute(
		id, userID, conversation.NewChannel(channel),
		conversation.Status(status), createdAt, messages,
	), nil
}

func (r *ConversationRepository) loadMessages(ctx context.Context, id conversation.SessionID) ([]conversation.Message, error) {
	const q = `
		SELECT id, session_id, role, content, COALESCE(msg_type, ''), created_at
		FROM (
			SELECT id, session_id, role, content, msg_type, created_at
			FROM messages
			WHERE session_id = $1
			ORDER BY created_at DESC
			LIMIT $2
		) recent
		ORDER BY created_at ASC`

	rows, err := r.pool.Query(ctx, q, id.UUID(), r.historyWindow)
	if err != nil {
		return nil, fmt.Errorf("conversation: load messages: %w", err)
	}
	defer rows.Close()

	var out []conversation.Message
	for rows.Next() {
		var (
			msgID     string
			sessID    string
			role      string
			content   string
			msgType   string
			createdAt time.Time
		)
		if err := rows.Scan(&msgID, &sessID, &role, &content, &msgType, &createdAt); err != nil {
			return nil, fmt.Errorf("conversation: scan message: %w", err)
		}
		out = append(out, conversation.ReconstituteMessage(
			parseMessageID(msgID),
			id,
			conversation.Role(role),
			content,
			conversation.MessageType(msgType),
			createdAt,
		))
	}
	return out, rows.Err()
}

func (r *ConversationRepository) Save(ctx context.Context, session *conversation.Session) error {
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("conversation: begin: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if session.IsPersisted() {
		const upd = `UPDATE chat_sessions SET status = $2 WHERE id = $1`
		if _, err := tx.Exec(ctx, upd, session.ID().UUID(), string(session.Status())); err != nil {
			return fmt.Errorf("conversation: update session: %w", err)
		}
	} else {
		const ins = `INSERT INTO chat_sessions (id, user_id, channel, status, created_at) VALUES ($1, $2, $3, $4, $5)`
		if _, err := tx.Exec(ctx, ins,
			session.ID().UUID(), session.UserID().String(), session.Channel().String(),
			string(session.Status()), session.CreatedAt(),
		); err != nil {
			return fmt.Errorf("conversation: insert session: %w", err)
		}
	}

	const insMsg = `INSERT INTO messages (id, session_id, role, content, msg_type, created_at) VALUES ($1, $2, $3, $4, $5, $6)`
	for _, m := range session.PendingMessages() {
		var msgType *string
		if t := m.Type().String(); t != "" {
			msgType = &t
		}
		if _, err := tx.Exec(ctx, insMsg,
			m.ID().UUID(), session.ID().UUID(), string(m.Role()), m.Content().String(), msgType, m.CreatedAt(),
		); err != nil {
			return fmt.Errorf("conversation: insert message: %w", err)
		}
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("conversation: commit: %w", err)
	}
	session.MarkPersisted()
	return nil
}

func (r *ConversationRepository) LastActivityAt(ctx context.Context, id conversation.SessionID) (time.Time, error) {
	const q = `SELECT created_at FROM messages WHERE session_id = $1 ORDER BY created_at DESC LIMIT 1`
	var ts time.Time
	err := r.pool.QueryRow(ctx, q, id.UUID()).Scan(&ts)
	if errors.Is(err, pgx.ErrNoRows) {
		return time.Time{}, nil
	}
	if err != nil {
		return time.Time{}, fmt.Errorf("conversation: last activity: %w", err)
	}
	return ts, nil
}
