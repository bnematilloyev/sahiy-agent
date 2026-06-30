// Package support is the bounded context for human-operator handoff. Its
// aggregate root is Ticket, which tracks a support request through its
// open -> in_progress -> closed lifecycle.
package support

import (
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/conversation"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// TicketID is the identity value object of the Ticket aggregate.
type TicketID struct{ value uuid.UUID }

// NewTicketID generates a fresh identity.
func NewTicketID() TicketID { return TicketID{value: uuid.New()} }

// TicketIDFromUUID adapts a uuid.UUID into the VO.
func TicketIDFromUUID(id uuid.UUID) TicketID { return TicketID{value: id} }

// UUID returns the underlying uuid.UUID.
func (t TicketID) UUID() uuid.UUID { return t.value }

// String returns the canonical textual form.
func (t TicketID) String() string { return t.value.String() }

// Status is the lifecycle state of a ticket.
type Status string

const (
	StatusOpen       Status = "open"
	StatusInProgress Status = "in_progress"
	StatusClosed     Status = "closed"
)

// Type classifies a support request (e.g. "operator", "complaint"). It is a
// value object, normalized and defaulted on construction.
type Type struct{ value string }

// NewType normalizes a ticket type, defaulting to "operator" when blank.
func NewType(raw string) Type {
	v := strings.ToLower(strings.TrimSpace(raw))
	if v == "" {
		v = "operator"
	}
	return Type{value: v}
}

// String returns the type name.
func (t Type) String() string { return t.value }

// Ticket is the aggregate root for a support handoff.
type Ticket struct {
	id         TicketID
	sessionID  conversation.SessionID
	userID     shared.UserID
	ticketType Type
	status     Status
	operatorID string
	createdAt  time.Time
}

// Open creates a new open ticket for a session.
func Open(sessionID conversation.SessionID, userID shared.UserID, ticketType Type) *Ticket {
	return &Ticket{
		id:         NewTicketID(),
		sessionID:  sessionID,
		userID:     userID,
		ticketType: ticketType,
		status:     StatusOpen,
		createdAt:  time.Now(),
	}
}

// Reconstitute rebuilds a Ticket from persisted state.
func Reconstitute(id TicketID, sessionID conversation.SessionID, userID shared.UserID, ticketType Type, status Status, operatorID string, createdAt time.Time) *Ticket {
	return &Ticket{
		id:         id,
		sessionID:  sessionID,
		userID:     userID,
		ticketType: ticketType,
		status:     status,
		operatorID: operatorID,
		createdAt:  createdAt,
	}
}

// AssignOperator moves the ticket to in_progress under the given operator.
func (t *Ticket) AssignOperator(operatorID string) {
	t.operatorID = strings.TrimSpace(operatorID)
	if t.status == StatusOpen {
		t.status = StatusInProgress
	}
}

// Close marks the ticket closed (idempotent).
func (t *Ticket) Close() { t.status = StatusClosed }

// IsOpen reports whether the ticket is not yet closed.
func (t *Ticket) IsOpen() bool { return t.status != StatusClosed }

// --- getters ---

func (t *Ticket) ID() TicketID                      { return t.id }
func (t *Ticket) SessionID() conversation.SessionID { return t.sessionID }
func (t *Ticket) UserID() shared.UserID             { return t.userID }
func (t *Ticket) Type() Type                        { return t.ticketType }
func (t *Ticket) Status() Status                    { return t.status }
func (t *Ticket) OperatorID() string                { return t.operatorID }
func (t *Ticket) CreatedAt() time.Time              { return t.createdAt }
