// Package conversation is the bounded context that owns chat sessions and their
// messages. Its aggregate root is Session, which guards the invariants around
// appending messages and the open/closed lifecycle.
package conversation

import "github.com/google/uuid"

// SessionID is the identity value object of the Session aggregate.
type SessionID struct {
	value uuid.UUID
}

// NewSessionID generates a fresh identity.
func NewSessionID() SessionID { return SessionID{value: uuid.New()} }

// ParseSessionID parses a textual UUID into a SessionID.
func ParseSessionID(raw string) (SessionID, bool) {
	id, err := uuid.Parse(raw)
	if err != nil {
		return SessionID{}, false
	}
	return SessionID{value: id}, true
}

// SessionIDFromUUID adapts a uuid.UUID (e.g. from persistence) into the VO.
func SessionIDFromUUID(id uuid.UUID) SessionID { return SessionID{value: id} }

// UUID returns the underlying uuid.UUID for persistence and transport.
func (s SessionID) UUID() uuid.UUID { return s.value }

// String returns the canonical textual form.
func (s SessionID) String() string { return s.value.String() }

// IsZero reports whether the identity is unset.
func (s SessionID) IsZero() bool { return s.value == uuid.Nil }

// MessageID is the identity value object of the Message entity.
type MessageID struct {
	value uuid.UUID
}

// NewMessageID generates a fresh identity.
func NewMessageID() MessageID { return MessageID{value: uuid.New()} }

// MessageIDFromUUID adapts a uuid.UUID into the VO.
func MessageIDFromUUID(id uuid.UUID) MessageID { return MessageID{value: id} }

// UUID returns the underlying uuid.UUID.
func (m MessageID) UUID() uuid.UUID { return m.value }

// String returns the canonical textual form.
func (m MessageID) String() string { return m.value.String() }
