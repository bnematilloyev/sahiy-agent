package conversation

import "github.com/sahiy-backend/sahiy-agent/internal/domain/shared"

// SessionOpened is recorded when a new session is started.
type SessionOpened struct {
	shared.BaseEvent
	SessionID SessionID
	UserID    shared.UserID
	Channel   Channel
}

// EventName implements shared.DomainEvent.
func (SessionOpened) EventName() string { return "conversation.session_opened" }

// MessageAppended is recorded when a message is added to a session.
type MessageAppended struct {
	shared.BaseEvent
	SessionID SessionID
	MessageID MessageID
	Role      Role
}

// EventName implements shared.DomainEvent.
func (MessageAppended) EventName() string { return "conversation.message_appended" }

// SessionClosed is recorded when a session is closed.
type SessionClosed struct {
	shared.BaseEvent
	SessionID SessionID
}

// EventName implements shared.DomainEvent.
func (SessionClosed) EventName() string { return "conversation.session_closed" }
