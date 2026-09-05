package embedding

import (
	"log/slog"

	"github.com/sahiy-backend/sahiy-agent/internal/config"
)

// NewEmbedder builds the embedding chain from configuration. With no real
// embedding provider configured, this is always the mock embedder: FAQ
// retrieval then relies entirely on lexical search (see faq.Service.retrieve).
func NewEmbedder(cfg config.AI, log *slog.Logger) *FallbackEmbedder {
	chain := NewFallbackEmbedder(log)
	chain.Add("mock", NewMockEmbedder(cfg.EmbeddingDim))
	return chain
}
