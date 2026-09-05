package embedding

import (
	"context"
	"log/slog"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
)

// FallbackEmbedder tries each embedder in order, returning the first success.
// It always has the mock embedder as a last resort, so the service keeps
// running (with retrieval falling back to lexical search) with no real
// embedding provider configured.
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

// Embed tries each embedder in order. Reaching the mock is reported as a
// degraded result rather than passed off as a real embedding: callers must be
// able to tell, or they would run a meaningless vector search over hash-derived
// vectors and conclude the knowledge base is empty.
func (e *FallbackEmbedder) Embed(ctx context.Context, text string) (ai.Embedding, error) {
	var lastErr error
	for _, n := range e.embedders {
		out, err := n.embedder.Embed(ctx, text)
		if err == nil {
			out.Degraded = out.Degraded || n.name == mockEmbedderName
			return out, nil
		}
		lastErr = err
		e.log.Warn("embedder failed, falling back", "embedder", n.name, "error", err)
	}
	return ai.Embedding{}, lastErr
}

// UsesMockOnly reports whether the chain has no real embedding provider at all.
// This is the startup-time view; a real provider can still fail per request, in
// which case Embed reports Degraded.
func (e *FallbackEmbedder) UsesMockOnly() bool {
	for _, n := range e.embedders {
		if n.name != mockEmbedderName {
			return false
		}
	}
	return true
}
