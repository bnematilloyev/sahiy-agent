package embedding

import (
	"log/slog"

	"github.com/sahiy-backend/sahiy-agent/internal/config"
)

// NewEmbedder builds the fallback embedding chain from configuration. It always
// ends in the mock embedder, so the returned FallbackEmbedder is never empty.
func NewEmbedder(cfg config.AI, log *slog.Logger) *FallbackEmbedder {
	chain := NewFallbackEmbedder(log)
	for _, name := range cfg.EmbeddingChainProviders() {
		switch name {
		case "openai":
			if cfg.HasOpenAI() {
				chain.Add("openai", NewOpenAIEmbedder(cfg.OpenAIKey, cfg.OpenAIEmbedding, cfg.Timeout))
			}
		case "mock":
			chain.Add("mock", NewMockEmbedder(cfg.EmbeddingDim))
		}
	}
	// Guarantee at least the mock embedder is present.
	if len(chain.embedders) == 0 {
		chain.Add("mock", NewMockEmbedder(cfg.EmbeddingDim))
	}
	return chain
}
