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

	// The fields below describe how the answer was produced. They do not
	// affect what the customer sees; they exist so the turn can be recorded
	// for the learning loop.

	// Route is the route that handled the message ("faq", "api", ...).
	Route string
	// Language is the reply language code.
	Language string
	// Degraded reports that no real model answered - the rules fallback did.
	Degraded bool
}
