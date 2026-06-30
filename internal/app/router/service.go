// Package router is the application service that decides a message's route. It
// prefers an LLM classification and reconciles it with deterministic signals
// (operator request, track number), falling back to pure keyword routing when
// the LLM is unavailable.
package router

import (
	"context"
	"encoding/json"
	"log/slog"
	"strings"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/conversation"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/routing"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

const historyLimit = 10

// Service decides routes.
type Service struct {
	completer ai.Completer
	log       *slog.Logger
}

// New constructs the router service.
func New(completer ai.Completer, log *slog.Logger) *Service {
	return &Service{completer: completer, log: log}
}

// Decide returns the routing decision for the current message.
func (s *Service) Decide(ctx context.Context, history []conversation.Message, text string, meta map[string]any) routing.Decision {
	lang := resolveLanguage(text, meta)

	// Deterministic hard overrides take precedence over the LLM.
	if routing.IsOperatorRequest(text) {
		return routing.Decision{Route: routing.RouteTicket, Language: lang}
	}
	if track, ok := routing.ExtractTrack(text); ok {
		return routing.Decision{Route: routing.RouteAPI, Language: lang, SearchQuery: track}
	}

	if s.completer.Available() {
		if decision, ok := s.decideWithLLM(ctx, history, text, lang); ok {
			return decision
		}
	}

	return routing.Decision{Route: routing.FallbackRoute(text), Language: lang}
}

func (s *Service) decideWithLLM(ctx context.Context, history []conversation.Message, text string, lang shared.Language) (routing.Decision, bool) {
	req := ai.CompletionRequest{
		System:      ai.RouterSystemPrompt(),
		Messages:    []ai.Message{{Role: ai.RoleUser, Content: ai.BuildRouterUser(toAIMessages(history), text)}},
		MaxTokens:   200,
		Temperature: 0,
	}
	raw, err := s.completer.Complete(ctx, req)
	if err != nil {
		s.log.Warn("router: llm failed, using fallback", "error", err)
		return routing.Decision{}, false
	}

	parsed, ok := parseRouterJSON(raw)
	if !ok {
		s.log.Warn("router: could not parse llm output, using fallback", "raw", raw)
		return routing.Decision{}, false
	}

	decision := routing.Decision{
		Route:       routing.ParseRoute(parsed.Route),
		Language:    lang,
		SearchQuery: parsed.SearchQuery,
	}
	if parsed.ReplyLanguage != "" {
		decision.Language = shared.NewLanguage(parsed.ReplyLanguage)
	}
	return decision, true
}

type routerJSON struct {
	Route         string `json:"route"`
	ReplyLanguage string `json:"reply_language"`
	SearchQuery   string `json:"search_query"`
}

// parseRouterJSON extracts the JSON object from the model output, tolerating any
// surrounding prose or code fences.
func parseRouterJSON(raw string) (routerJSON, bool) {
	start := strings.IndexByte(raw, '{')
	end := strings.LastIndexByte(raw, '}')
	if start < 0 || end <= start {
		return routerJSON{}, false
	}
	var out routerJSON
	if err := json.Unmarshal([]byte(raw[start:end+1]), &out); err != nil {
		return routerJSON{}, false
	}
	if out.Route == "" {
		return routerJSON{}, false
	}
	return out, true
}

// resolveLanguage uses an explicit reply_language hint from metadata when valid,
// otherwise detects the language from the message text.
func resolveLanguage(text string, meta map[string]any) shared.Language {
	if meta != nil {
		if hint, ok := meta["reply_language"].(string); ok && strings.TrimSpace(hint) != "" {
			return shared.NewLanguage(hint)
		}
	}
	return shared.DetectLanguage(text)
}

func toAIMessages(history []conversation.Message) []ai.Message {
	if len(history) > historyLimit {
		history = history[len(history)-historyLimit:]
	}
	out := make([]ai.Message, 0, len(history))
	for _, m := range history {
		out = append(out, ai.Message{Role: string(m.Role()), Content: m.Content().String()})
	}
	return out
}
