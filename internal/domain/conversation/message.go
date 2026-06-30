package conversation

import "time"

// Role identifies who authored a message.
type Role string

const (
	RoleUser      Role = "user"
	RoleAssistant Role = "assistant"
)

// MessageType is the classification stored on a message (and surfaced as the
// HTTP response `type`). The zero value is an unset type.
type MessageType string

const (
	MessageTypeAuto   MessageType = "auto"
	MessageTypeAPI    MessageType = "api"
	MessageTypeTicket MessageType = "ticket"
	MessageTypeError  MessageType = "error"
)

// String returns the wire value.
func (t MessageType) String() string { return string(t) }

// Message is an entity inside the Session aggregate. Its identity is MessageID;
// it is only ever created and mutated through the aggregate root.
type Message struct {
	id        MessageID
	sessionID SessionID
	role      Role
	content   Content
	msgType   MessageType
	createdAt time.Time
}

// ReconstituteMessage rebuilds a Message from persisted state. Used by
// repositories only.
func ReconstituteMessage(id MessageID, sessionID SessionID, role Role, content string, msgType MessageType, createdAt time.Time) Message {
	return Message{
		id:        id,
		sessionID: sessionID,
		role:      role,
		content:   contentFromStore(content),
		msgType:   msgType,
		createdAt: createdAt,
	}
}

// ID returns the message identity.
func (m Message) ID() MessageID { return m.id }

// SessionID returns the owning session identity.
func (m Message) SessionID() SessionID { return m.sessionID }

// Role returns the author role.
func (m Message) Role() Role { return m.role }

// Content returns the message body.
func (m Message) Content() Content { return m.content }

// Type returns the message classification.
func (m Message) Type() MessageType { return m.msgType }

// CreatedAt returns when the message was created.
func (m Message) CreatedAt() time.Time { return m.createdAt }
