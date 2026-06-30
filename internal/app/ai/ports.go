// Package ai declares the application-layer ports for large-language-model
// completion and text embedding. Concrete adapters live under internal/infra and
// are selected at startup based on configuration.
package ai

import "context"

// Role names for chat messages sent to a Completer.
const (
	RoleSystem    = "system"
	RoleUser      = "user"
	RoleAssistant = "assistant"
)

// Message is one turn in a completion request.
type Message struct {
	Role    string
	Content string
}

// CompletionRequest is a single prompt to a Completer.
type CompletionRequest struct {
	// System is the system prompt (instructions). May be empty.
	System string
	// Messages is the conversation history plus the current user turn.
	Messages []Message
	// MaxTokens caps the response length (0 = provider default).
	MaxTokens int
	// Temperature controls randomness (0 = deterministic-ish).
	Temperature float64
}

// Completer produces a text completion from a chat-style prompt.
type Completer interface {
	// Complete returns the assistant's text reply.
	Complete(ctx context.Context, req CompletionRequest) (string, error)
	// Available reports whether the completer can currently serve requests
	// (e.g. has credentials). A rules-based fallback always returns true.
	Available() bool
}

// Embedder turns text into a dense vector for similarity search.
type Embedder interface {
	Embed(ctx context.Context, text string) ([]float32, error)
}
