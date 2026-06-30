package conversation

import (
	"context"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// Repository is the persistence port for the Session aggregate. Implementations
// live in the infrastructure layer. Sessions are loaded and saved as a unit;
// FindByID/FindActive hydrate the aggregate with its recent message window.
type Repository interface {
	// FindByID returns the session, or (nil, nil) when it does not exist.
	FindByID(ctx context.Context, id SessionID) (*Session, error)
	// FindActive returns the user's active session on the channel, or (nil, nil).
	FindActive(ctx context.Context, userID shared.UserID, channel Channel) (*Session, error)
	// Save inserts a new session or updates an existing one, persisting any
	// pending messages, then marks the aggregate clean.
	Save(ctx context.Context, session *Session) error
	// LastActivityAt returns the timestamp of the most recent message, or the
	// zero time when the session has none.
	LastActivityAt(ctx context.Context, id SessionID) (time.Time, error)
}
