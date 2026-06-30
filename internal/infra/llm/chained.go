package llm

import (
	"context"
	"errors"
	"log/slog"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
)

// ChainedClient tries a list of real providers in order, falling back to the
// rules client when they all fail (or none are configured). This implements the
// Anthropic -> OpenAI -> rules failover behavior of the Python service.
type ChainedClient struct {
	providers []namedCompleter
	fallback  ai.Completer
	log       *slog.Logger
}

type namedCompleter struct {
	name      string
	completer ai.Completer
}

// NewChainedClient builds the failover chain. providers should be the real LLM
// adapters in priority order; fallback is the always-available rules client.
func NewChainedClient(fallback ai.Completer, log *slog.Logger) *ChainedClient {
	return &ChainedClient{fallback: fallback, log: log}
}

// Add appends a named real provider to the chain.
func (c *ChainedClient) Add(name string, completer ai.Completer) {
	c.providers = append(c.providers, namedCompleter{name: name, completer: completer})
}

// Available reports whether at least one real provider can serve requests. The
// router uses this to choose between LLM-first and deterministic routing.
func (c *ChainedClient) Available() bool {
	for _, p := range c.providers {
		if p.completer.Available() {
			return true
		}
	}
	return false
}

// Complete tries each available provider in order, then the rules fallback.
func (c *ChainedClient) Complete(ctx context.Context, req ai.CompletionRequest) (string, error) {
	var lastErr error
	for _, p := range c.providers {
		if !p.completer.Available() {
			continue
		}
		text, err := p.completer.Complete(ctx, req)
		if err == nil {
			return text, nil
		}
		lastErr = err
		c.log.Warn("llm provider failed, falling back", "provider", p.name, "error", err)
	}
	if c.fallback != nil {
		return c.fallback.Complete(ctx, req)
	}
	if lastErr == nil {
		lastErr = errors.New("llm: no providers configured")
	}
	return "", lastErr
}
