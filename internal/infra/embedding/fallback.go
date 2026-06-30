package embedding

import (
	"context"
	"log/slog"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
)

// FallbackEmbedder tries each embedder in order, returning the first success.
// Wiring OpenAI then Mock means the service still functions (with weaker
// similarity) when the embeddings API is unavailable.
type FallbackEmbedder struct {
	embedders []named
	log       *slog.Logger
}

type named struct {
	name     string
	embedder ai.Embedder
}

// NewFallbackEmbedder constructs an empty fallback chain.
func NewFallbackEmbedder(log *slog.Logger) *FallbackEmbedder {
	return &FallbackEmbedder{log: log}
}

// Add appends a named embedder to the chain.
func (e *FallbackEmbedder) Add(name string, emb ai.Embedder) {
	e.embedders = append(e.embedders, named{name: name, embedder: emb})
}

// Embed tries each embedder in order.
func (e *FallbackEmbedder) Embed(ctx context.Context, text string) ([]float32, error) {
	var lastErr error
	for _, n := range e.embedders {
		vec, err := n.embedder.Embed(ctx, text)
		if err == nil {
			return vec, nil
		}
		lastErr = err
		e.log.Warn("embedder failed, falling back", "embedder", n.name, "error", err)
	}
	return nil, lastErr
}

// UsesMockOnly reports whether the chain has no real embedding provider, so
// callers can relax the similarity threshold.
func (e *FallbackEmbedder) UsesMockOnly() bool {
	for _, n := range e.embedders {
		if n.name != "mock" {
			return false
		}
	}
	return true
}
