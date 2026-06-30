package chat

import (
	"context"
	"fmt"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/conversation"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// ResetSession closes the user's active session on a channel (and its open
// tickets) so the next Reply opens a fresh conversation. Used by /new in Telegram.
func (s *ReplyService) ResetSession(ctx context.Context, userID string, channel string) error {
	uid, err := shared.NewUserID(userID)
	if err != nil {
		return err
	}
	ch := conversation.NewChannel(channel)

	active, err := s.sessions.FindActive(ctx, uid, ch)
	if err != nil {
		return fmt.Errorf("chat: find active session: %w", err)
	}
	if active == nil {
		return nil
	}

	active.Close()
	if s.tickets != nil {
		if err := s.tickets.CloseBySession(ctx, active.ID()); err != nil {
			s.log.Warn("chat: close tickets on reset", "session_id", active.ID().String(), "error", err)
		}
	}
	if err := s.sessions.Save(ctx, active); err != nil {
		return fmt.Errorf("chat: save closed session: %w", err)
	}
	s.events.Publish(ctx, active.PullEvents())
	return nil
}
