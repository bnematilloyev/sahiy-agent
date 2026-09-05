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
	// Route names the calling application flow (e.g. "rag", "generic", "order",
	// "router"). It carries no meaning to the provider; it is only there so
	// token-usage accounting can be broken down by flow.
	Route string
}

// Completion is a Completer's answer plus the quality signals the application
// layer needs to decide whether the reply can be trusted.
type Completion struct {
	// Text is the assistant's reply.
	Text string
	// Degraded reports that no real model produced this text: every configured
	// provider failed (or none is configured) and a canned fallback answered.
	// A degraded reply must never be presented to a customer as a real answer -
	// callers are expected to escalate to a human operator instead.
	Degraded bool
	// Usage is the provider's token accounting for this call. Zero-valued when
	// the provider gave no usage data (e.g. the degraded fallback).
	Usage Usage
	// Model is the concrete model that produced this completion (e.g.
	// "claude-haiku-4-5-20251001"). Empty when no real provider answered.
	Model string
}

// Usage is a provider's token accounting for one completion call.
type Usage struct {
	InputTokens              int
	OutputTokens             int
	CacheReadInputTokens     int
	CacheCreationInputTokens int
}

// UsageRecord is one completion's token accounting plus enough context (who
// called, which model, for which session) to make it useful in aggregate and
// to trace an unexpected spend back to the conversation that caused it.
type UsageRecord struct {
	Provider string
	Model    string
	Route    string
	// SessionID is the chat session this call served, or "" for calls made
	// outside a session.
	SessionID string
	Usage     Usage
}

// UsageRecorder persists token usage for later cost/volume reporting. Recording
// is best-effort: implementations must not let a slow or failing sink affect
// the caller's response, so RecordUsage takes no error return and is expected
// to handle its own timeout/async behavior internally.
type UsageRecorder interface {
	RecordUsage(ctx context.Context, rec UsageRecord)
}

// Completer produces a text completion from a chat-style prompt.
type Completer interface {
	// Complete returns the assistant's reply. A non-nil error means no reply at
	// all; a reply with Degraded set means "answered, but not by a model".
	Complete(ctx context.Context, req CompletionRequest) (Completion, error)
	// Available reports whether the completer can currently serve requests
	// (e.g. has credentials). A rules-based fallback always returns true.
	Available() bool
}

// Embedding is a vector plus the quality signal callers need to decide whether
// a similarity search over it means anything.
type Embedding struct {
	// Vector is the dense representation of the input text.
	Vector []float32
	// Degraded reports that no real embedding provider produced this vector -
	// it came from the deterministic mock. Cosine distance between mock vectors
	// carries no semantic meaning, so a vector search over them is worthless and
	// callers should fall back to lexical search instead.
	Degraded bool
}

// Embedder turns text into a dense vector for similarity search.
type Embedder interface {
	Embed(ctx context.Context, text string) (Embedding, error)
}
