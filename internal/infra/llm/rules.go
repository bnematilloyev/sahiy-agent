package llm

import (
	"context"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
)

// RulesClient is a no-API fallback Completer. It cannot truly reason, so it
// returns a polite deflection that the FAQ service treats as low confidence,
// which in turn triggers handoff to a human operator.
type RulesClient struct{}

// NewRulesClient constructs the fallback completer.
func NewRulesClient() *RulesClient { return &RulesClient{} }

// Available always returns true: the rules fallback is the last resort and is
// always ready.
func (c *RulesClient) Available() bool { return true }

// Complete returns a fixed deflection message.
func (c *RulesClient) Complete(_ context.Context, _ ai.CompletionRequest) (string, error) {
	return "Kechirasiz, hozir bu savolga aniq javob bera olmadim. " +
		"Iltimos, savolingizni boshqacha yozing yoki operator bilan bog'lanishingiz mumkin.", nil
}
