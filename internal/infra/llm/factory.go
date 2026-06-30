package llm

import (
	"log/slog"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
	"github.com/sahiy-backend/sahiy-agent/internal/config"
)

// NewCompleter builds the failover chain from configuration. The chain always
// ends in the rules fallback, so the returned Completer is never nil and
// Complete never leaves the caller without a reply.
func NewCompleter(cfg config.AI, log *slog.Logger) ai.Completer {
	chain := NewChainedClient(NewRulesClient(), log)
	for _, name := range cfg.ChainProviders() {
		switch name {
		case "anthropic":
			if cfg.HasAnthropic() {
				chain.Add("anthropic", NewAnthropicClient(cfg.AnthropicKey, cfg.AnthropicModel, cfg.Timeout))
			}
		case "openai":
			if cfg.HasOpenAI() {
				chain.Add("openai", NewOpenAIClient(cfg.OpenAIKey, cfg.OpenAIModel, cfg.Timeout))
			}
		}
	}
	return chain
}
