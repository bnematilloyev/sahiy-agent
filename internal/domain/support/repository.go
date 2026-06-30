package support

import (
	"context"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/conversation"
)

// Repository is the persistence port for the Ticket aggregate.
type Repository interface {
	// Save inserts or updates a ticket.
	Save(ctx context.Context, ticket *Ticket) error
	// FindOpenBySession returns the latest non-closed ticket for a session, or
	// (nil, nil) when there is none.
	FindOpenBySession(ctx context.Context, sessionID conversation.SessionID) (*Ticket, error)
	// CloseBySession closes all non-closed tickets for a session.
	CloseBySession(ctx context.Context, sessionID conversation.SessionID) error
}
