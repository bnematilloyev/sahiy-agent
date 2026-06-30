// Package order is the application service for answering order/parcel inquiries.
// It resolves order data via the Sahiy API and synthesizes a natural-language
// reply through the LLM.
package order

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/identity"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/order"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// CustomerLookup is the port this service uses to query the Sahiy API.
// The concrete implementation lives in internal/infra/sahiy.CustomerAPI.
type CustomerLookup interface {
	Lookup(ctx context.Context, req order.LookupRequest) (order.CustomerSnapshot, error)
}

// Result is the service's response for one order-inquiry turn.
type Result struct {
	Text          string
	Confidence    shared.Confidence
	Escalate      bool
	HandoffReason shared.HandoffReason
}

// Service answers order-related questions by fetching live order data from the
// Sahiy API and asking the LLM to compose a reply in the requested language.
type Service struct {
	lookup    CustomerLookup
	completer ai.Completer
	maxTokens int
	log       *slog.Logger
}

// New constructs the order service.
func New(lookup CustomerLookup, completer ai.Completer, maxTokens int, log *slog.Logger) *Service {
	if maxTokens <= 0 {
		maxTokens = 1024
	}
	return &Service{
		lookup:    lookup,
		completer: completer,
		maxTokens: maxTokens,
		log:       log,
	}
}

// Respond resolves the customer's order data and asks the LLM to formulate a
// reply. When the lookup fails or finds nothing, it escalates to a human
// operator with a polite localized message.
func (s *Service) Respond(ctx context.Context, query string, lang shared.Language, meta map[string]any) (Result, error) {
	id := identity.FromMetadata(meta)
	snapshot, err := s.lookup.Lookup(ctx, order.LookupRequest{
		Query:          query,
		VerifiedUserID: id.SahiyUserID,
		VerifiedPhone:  id.Phone,
	})
	if err != nil {
		s.log.Warn("order: lookup error", "error", err, "query", query)
		return s.escalate(lang), nil
	}
	if snapshot.IsEmpty() {
		s.log.Debug("order: snapshot empty", "query", query)
		return s.escalate(lang), nil
	}

	orderContext := order.Summarize(snapshot, lang)
	req := ai.CompletionRequest{
		System:      ai.OrderSystemPrompt(lang),
		Messages:    []ai.Message{{Role: ai.RoleUser, Content: ai.BuildOrderUser(orderContext, query)}},
		MaxTokens:   s.maxTokens,
		Temperature: 0.2,
	}
	text, err := s.completer.Complete(ctx, req)
	if err != nil {
		return Result{}, fmt.Errorf("order: llm completion: %w", err)
	}
	return Result{
		Text:          text,
		Confidence:    shared.NewConfidence(0.95),
		Escalate:      false,
		HandoffReason: shared.NoHandoff,
	}, nil
}

// escalate returns a polite "couldn't find your order" outcome that triggers
// handoff to a human operator.
func (s *Service) escalate(lang shared.Language) Result {
	return Result{
		Text:          orderNotFoundMessage(lang),
		Confidence:    shared.NewConfidence(0.2),
		Escalate:      true,
		HandoffReason: shared.HandoffOperatorRequest,
	}
}

func orderNotFoundMessage(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "Не удалось найти ваш заказ. Пожалуйста, укажите номер телефона или трек-номер. Подключаю оператора."
	case shared.LangEn.Code():
		return "Could not find your order. Please provide your phone number or tracking number. Connecting an operator."
	case shared.LangCyr.Code():
		return "Buyurtmangiz topilmadi. Телефон рақамингиз ёки track рақамингизни юборинг. Оператор уланмоқда."
	case shared.LangZh.Code():
		return "找不到您的订单。请提供您的电话号码或快递单号。正在为您接通客服人员。"
	default: // uz
		return "Buyurtmangiz topilmadi. Iltimos, telefon yoki track raqamingizni yuboring. Operator bilan bog'layapman."
	}
}
