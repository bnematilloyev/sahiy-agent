// Package chat is the application layer for the conversation use case. It
// orchestrates the conversation aggregate, delegates answer generation to a
// Responder strategy, and translates between transport DTOs and the domain.
package chat

// ReplyCommand is the input to the Reply use case. It carries raw transport
// values; the use case turns them into domain value objects.
type ReplyCommand struct {
	// SessionID is the caller-provided session identifier (may be empty).
	SessionID string
	UserID    string
	Text      string
	Channel   string
	Metadata  map[string]any
}
