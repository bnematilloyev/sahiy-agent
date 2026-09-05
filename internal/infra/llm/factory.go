package llm

import (
	"log/slog"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
	"github.com/sahiy-backend/sahiy-agent/internal/config"
)

// NewCompleter builds the failover chain from configuration. The chain always
// ends in the rules fallback, so the returned Completer is never nil and
// Complete never leaves the caller without a reply. recorder may be nil.
func NewCompleter(cfg config.AI, recorder ai.UsageRecorder, log *slog.Logger) ai.Completer {
	chain := NewChainedClient(NewRulesClient(), recorder, cfg.MaxConcurrent, log)
	for _, name := range cfg.ChainProviders() {
		if name == "anthropic" && cfg.HasAnthropic() {
			chain.Add("anthropic", NewAnthropicClient(cfg.AnthropicKey, cfg.AnthropicModel, cfg.Timeout))
		}
	}
	return chain
}
