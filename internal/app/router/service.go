// Package router is the application service that decides a message's route. It
// prefers an LLM classification and reconciles it with deterministic signals
// (operator request, track number), falling back to pure keyword routing when
// the LLM is unavailable.
package router

import (
	"context"
	"encoding/json"
	"log/slog"

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
	lang, langCertain := resolveLanguage(text, meta, history)

	// Deterministic hard overrides take precedence over the LLM.
	if routing.IsOperatorRequest(text) {
		return routing.Decision{Route: routing.RouteTicket, Language: lang}
	}
	if track, ok := routing.ExtractTrack(text); ok {
		return routing.Decision{Route: routing.RouteAPI, Language: lang, SearchQuery: track}
	}

	if s.completer.Available() {
		if decision, ok := s.decideWithLLM(ctx, history, text, lang, langCertain); ok {
			return decision
		}
	}

	return routing.Decision{Route: routing.FallbackRoute(text), Language: lang}
}

func (s *Service) decideWithLLM(ctx context.Context, history []conversation.Message, text string, lang shared.Language, langCertain bool) (routing.Decision, bool) {
	req := ai.CompletionRequest{
		System:      ai.RouterSystemPrompt(),
		Messages:    []ai.Message{{Role: ai.RoleUser, Content: ai.BuildRouterUser(toAIMessages(history), text)}},
		MaxTokens:   200,
		Temperature: 0,
		Route:       "router",
	}
	out, err := s.completer.Complete(ctx, req)
	if err != nil {
		s.log.Warn("router: llm failed, using fallback", "error", err)
		return routing.Decision{}, false
	}
	if out.Degraded {
		// No real model classified this message; keyword routing is more
		// trustworthy than a canned placeholder.
		return routing.Decision{}, false
	}

	parsed, ok := parseRouterJSON(out.Text)
	if !ok {
		s.log.Warn("router: could not parse llm output, using fallback", "raw", out.Text)
		return routing.Decision{}, false
	}

	decision := routing.Decision{
		Route:       routing.ParseRoute(parsed.Route),
		Language:    lang,
		SearchQuery: parsed.SearchQuery,
	}
	// The word-list detector is deterministic and tested; the model's guess only
	// fills in when the message itself gave us nothing to go on.
	if parsed.ReplyLanguage != "" && !langCertain {
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
	obj, ok := ai.ExtractJSONObject(raw)
	if !ok {
		return routerJSON{}, false
	}
	var out routerJSON
	if err := json.Unmarshal([]byte(obj), &out); err != nil {
		return routerJSON{}, false
	}
	if out.Route == "" {
		return routerJSON{}, false
	}
	return out, true
}

// resolveLanguage decides which language to answer in. What the customer just
// wrote wins over their stored preference: someone who switches language expects
// the reply to switch too. When the current message is inconclusive the stored
// preference applies, then the language of their earlier messages.
// The bool reports whether the current message itself was decisive; when it is,
// the LLM's own language guess must not override it.
func resolveLanguage(text string, meta map[string]any, history []conversation.Message) (shared.Language, bool) {
	if lang, ok := shared.DetectReplyLanguage(text); ok {
		return lang, true
	}
	return shared.ResolveReplyLanguage(text, shared.LanguageHintFromMeta(meta), userTexts(history)), false
}

// userTexts extracts the customer's own turns, oldest first.
func userTexts(history []conversation.Message) []string {
	out := make([]string, 0, len(history))
	for _, m := range history {
		if m.Role() == conversation.RoleUser {
			out = append(out, m.Content().String())
		}
	}
	return out
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
