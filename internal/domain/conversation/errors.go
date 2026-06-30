package conversation

import "errors"

// Domain errors for the conversation context.
var (
	// ErrEmptyContent is returned when message content is blank.
	ErrEmptyContent = errors.New("conversation: message content must not be empty")
	// ErrSessionClosed is returned when appending to a closed session.
	ErrSessionClosed = errors.New("conversation: session is closed")
	// ErrAccessDenied is returned when a session is used by a different user.
	ErrAccessDenied = errors.New("conversation: session belongs to another user")
)
