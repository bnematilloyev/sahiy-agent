package chat

import (
	"github.com/sahiy-backend/sahiy-agent/internal/domain/conversation"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// Reply is the result of the Reply use case, expressed in domain value objects.
// Transport adapters map it to their own wire formats.
type Reply struct {
	SessionID     conversation.SessionID
	Type          conversation.MessageType
	Text          string
	Confidence    shared.Confidence
	Escalate      bool
	HandoffReason shared.HandoffReason
	TicketID      *string
	ChannelExtra  map[string]any
}
