package conversation

import (
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// now is overridable in tests so aggregate behavior is deterministic.
var now = time.Now

// Status is the lifecycle state of a session.
type Status string

const (
	StatusActive Status = "active"
	StatusClosed Status = "closed"
)

// Session is the aggregate root of the conversation context. It owns its
// Messages and is the only place where the rules around appending and the
// open/closed lifecycle are enforced.
type Session struct {
	id        SessionID
	userID    shared.UserID
	channel   Channel
	status    Status
	createdAt time.Time

	messages []Message // loaded chronological window
	pending  []Message // appended in this unit of work, not yet persisted

	persisted bool
	events    []shared.DomainEvent
}

// Open starts a brand-new active session and records a SessionOpened event.
func Open(userID shared.UserID, channel Channel) *Session {
	return OpenWithID(NewSessionID(), userID, channel)
}

// OpenWithID starts a new active session using a caller-provided identity. This
// maps an external identifier (the market's ai_session_id) onto a local session.
func OpenWithID(id SessionID, userID shared.UserID, channel Channel) *Session {
	s := &Session{
		id:        id,
		userID:    userID,
		channel:   channel,
		status:    StatusActive,
		createdAt: now(),
		persisted: false,
	}
	s.record(SessionOpened{
		BaseEvent: shared.BaseEvent{At: s.createdAt},
		SessionID: id,
		UserID:    userID,
		Channel:   channel,
	})
	return s
}

// Reconstitute rebuilds a previously persisted session. Used by repositories
// only; it records no events and is marked as already persisted.
func Reconstitute(id SessionID, userID shared.UserID, channel Channel, status Status, createdAt time.Time, messages []Message) *Session {
	return &Session{
		id:        id,
		userID:    userID,
		channel:   channel,
		status:    status,
		createdAt: createdAt,
		messages:  messages,
		persisted: true,
	}
}

// Append adds a message to the session, enforcing the open-session invariant.
// The created Message is returned and also buffered as pending until persisted.
func (s *Session) Append(role Role, content Content, msgType MessageType) (Message, error) {
	if s.status == StatusClosed {
		return Message{}, ErrSessionClosed
	}
	m := Message{
		id:        NewMessageID(),
		sessionID: s.id,
		role:      role,
		content:   content,
		msgType:   msgType,
		createdAt: now(),
	}
	s.messages = append(s.messages, m)
	s.pending = append(s.pending, m)
	s.record(MessageAppended{
		BaseEvent: shared.BaseEvent{At: m.createdAt},
		SessionID: s.id,
		MessageID: m.id,
		Role:      role,
	})
	return m, nil
}

// Close marks the session closed (idempotent) and records a SessionClosed event.
func (s *Session) Close() {
	if s.status == StatusClosed {
		return
	}
	s.status = StatusClosed
	s.record(SessionClosed{
		BaseEvent: shared.BaseEvent{At: now()},
		SessionID: s.id,
	})
}

// IsActive reports whether the session can still accept messages.
func (s *Session) IsActive() bool { return s.status == StatusActive }

// IsIdle reports whether the session has been silent for at least timeout since
// lastActivity. A non-positive timeout disables idle detection.
func (s *Session) IsIdle(lastActivity time.Time, timeout time.Duration) bool {
	if timeout <= 0 || lastActivity.IsZero() {
		return false
	}
	return now().Sub(lastActivity) >= timeout
}

// BelongsTo reports whether the session is owned by the given user.
func (s *Session) BelongsTo(userID shared.UserID) bool {
	return s.userID.String() == userID.String()
}

// --- getters ---

// ID returns the session identity.
func (s *Session) ID() SessionID { return s.id }

// UserID returns the owning user.
func (s *Session) UserID() shared.UserID { return s.userID }

// Channel returns the delivery channel.
func (s *Session) Channel() Channel { return s.channel }

// Status returns the lifecycle state.
func (s *Session) Status() Status { return s.status }

// CreatedAt returns the creation timestamp.
func (s *Session) CreatedAt() time.Time { return s.createdAt }

// Messages returns a copy of the loaded message window.
func (s *Session) Messages() []Message {
	out := make([]Message, len(s.messages))
	copy(out, s.messages)
	return out
}

// --- persistence support (used by repositories) ---

// IsPersisted reports whether the session row already exists in storage.
func (s *Session) IsPersisted() bool { return s.persisted }

// PendingMessages returns messages appended since the last persist.
func (s *Session) PendingMessages() []Message {
	out := make([]Message, len(s.pending))
	copy(out, s.pending)
	return out
}

// MarkPersisted clears the dirty state after a successful save.
func (s *Session) MarkPersisted() {
	s.persisted = true
	s.pending = nil
}

// --- domain events ---

func (s *Session) record(e shared.DomainEvent) { s.events = append(s.events, e) }

// PullEvents returns and clears the recorded domain events.
func (s *Session) PullEvents() []shared.DomainEvent {
	out := s.events
	s.events = nil
	return out
}
