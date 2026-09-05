package llm

import (
	"context"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
)

// RulesClient is a no-API fallback Completer used when every real provider is
// unavailable. It cannot reason, so it never pretends to answer: it returns a
// Completion marked Degraded, which the application layer turns into a handoff
// to a human operator (in the customer's own language).
type RulesClient struct{}

// NewRulesClient constructs the fallback completer.
func NewRulesClient() *RulesClient { return &RulesClient{} }

// Available always returns true: the rules fallback is the last resort and is
// always ready.
func (c *RulesClient) Available() bool { return true }

// Complete returns a degraded, non-answer. The text is a neutral placeholder -
// callers are expected to replace it with a localized operator handoff message
// rather than show it to the customer.
func (c *RulesClient) Complete(_ context.Context, _ ai.CompletionRequest) (ai.Completion, error) {
	return ai.Completion{Text: degradedPlaceholder, Degraded: true}, nil
}

// degradedPlaceholder is intentionally not customer-facing copy.
const degradedPlaceholder = "AI providers unavailable"
