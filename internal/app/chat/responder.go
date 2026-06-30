package chat

import (
	"context"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/conversation"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// Responder is the strategy that produces the assistant's answer for one turn.
// The application service owns session lifecycle and persistence; the Responder
// owns "what to say" (router + handler pipeline).
type Responder interface {
	Respond(ctx context.Context, session *conversation.Session, text string, meta map[string]any) (Outcome, error)
}

// Outcome is the Responder's answer plus AI-control signals.
type Outcome struct {
	Text          string
	Type          conversation.MessageType
	Confidence    shared.Confidence
	Escalate      bool
	HandoffReason shared.HandoffReason
	TicketID      *string
	ChannelExtra  map[string]any
}
