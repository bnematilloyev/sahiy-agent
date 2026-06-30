package postgres

import (
	"github.com/google/uuid"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/conversation"
)

// parseMessageID converts a textual UUID from storage into a MessageID. Stored
// ids are always valid, so a parse failure yields the zero value.
func parseMessageID(raw string) conversation.MessageID {
	id, err := uuid.Parse(raw)
	if err != nil {
		return conversation.MessageID{}
	}
	return conversation.MessageIDFromUUID(id)
}

// mustUUID parses a textual UUID coming from storage, returning the nil UUID on
// failure (stored ids are always valid).
func mustUUID(raw string) uuid.UUID {
	id, err := uuid.Parse(raw)
	if err != nil {
		return uuid.Nil
	}
	return id
}
