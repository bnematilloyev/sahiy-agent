package chat

import (
	"context"
	"log/slog"
	"strings"

	"github.com/sahiy-backend/sahiy-agent/internal/app/faq"
	"github.com/sahiy-backend/sahiy-agent/internal/app/router"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/conversation"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/routing"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

const chitchatConfidence = 0.95

// OrderHandler handles the "api" route (order/parcel/tracking inquiries).
type OrderHandler interface {
	Respond(ctx context.Context, query string, lang shared.Language, meta map[string]any) (Outcome, error)
}

// SupportHandler handles the "ticket" route and persists support tickets.
type SupportHandler interface {
	Respond(ctx context.Context, session *conversation.Session, text string, lang shared.Language, meta map[string]any) (Outcome, error)
}

// ProductSearchHandler handles the "product_search" route.
type ProductSearchHandler interface {
	Respond(ctx context.Context, query string, lang shared.Language) (Outcome, error)
}

// CategoryHandler handles the "category" route.
type CategoryHandler interface {
	Respond(ctx context.Context, query string, lang shared.Language) (Outcome, error)
}

// PickupHandler handles the "pickup" route.
type PickupHandler interface {
	Respond(ctx context.Context, query string, lang shared.Language) (Outcome, error)
}

// Handlers groups optional route handlers wired at startup. Nil handlers fall
// back to FAQ or generic escalation.
type Handlers struct {
	Order         OrderHandler
	Support       SupportHandler
	ProductSearch ProductSearchHandler
	Category      CategoryHandler
	Pickup        PickupHandler
}

// RouterResponder routes messages and dispatches to the appropriate handler.
type RouterResponder struct {
	router              *router.Service
	faq                 *faq.Service
	handlers            Handlers
	escalationThreshold float64
	log                 *slog.Logger
}

// NewRouterResponder wires the responder.
func NewRouterResponder(r *router.Service, f *faq.Service, handlers Handlers, escalationThreshold float64, log *slog.Logger) *RouterResponder {
	return &RouterResponder{
		router:              r,
		faq:                 f,
		handlers:            handlers,
		escalationThreshold: escalationThreshold,
		log:                 log,
	}
}

// Respond implements Responder.
func (r *RouterResponder) Respond(ctx context.Context, session *conversation.Session, text string, meta map[string]any) (Outcome, error) {
	history := priorMessages(session)
	decision := r.router.Decide(ctx, history, text, meta)
	r.log.Debug("route decided", "route", decision.Route.String(), "lang", decision.Language.Code())

	if decision.Route.Equals(routing.RouteTicket) {
		if r.handlers.Support != nil {
			return r.handlers.Support.Respond(ctx, session, text, decision.Language, meta)
		}
		return r.escalateToOperator(decision.Language), nil
	}

	if decision.Route.Equals(routing.RouteChitchat) {
		ans, err := r.faq.Respond(ctx, nil, text, decision.Language)
		if err != nil {
			return Outcome{}, err
		}
		return Outcome{
			Text:       ans.Text,
			Type:       conversation.MessageTypeAuto,
			Confidence: shared.NewConfidence(chitchatConfidence),
		}, nil
	}

	if decision.Route.Equals(routing.RouteAPI) && r.handlers.Order != nil {
		return r.handlers.Order.Respond(ctx, text, decision.Language, meta)
	}

	if decision.Route.Equals(routing.RouteProductSearch) && r.handlers.ProductSearch != nil {
		q := strings.TrimSpace(decision.SearchQuery)
		if q == "" {
			q = text
		}
		return r.handlers.ProductSearch.Respond(ctx, q, decision.Language)
	}

	if decision.Route.Equals(routing.RouteCategory) && r.handlers.Category != nil {
		return r.handlers.Category.Respond(ctx, text, decision.Language)
	}

	if decision.Route.Equals(routing.RoutePickup) && r.handlers.Pickup != nil {
		return r.handlers.Pickup.Respond(ctx, text, decision.Language)
	}

	ans, err := r.faq.Respond(ctx, history, text, decision.Language)
	if err != nil {
		return Outcome{}, err
	}
	out := Outcome{
		Text:       ans.Text,
		Type:       conversation.MessageTypeAuto,
		Confidence: ans.Confidence,
	}
	if ans.Confidence.Below(r.escalationThreshold) {
		out.Escalate = true
		out.HandoffReason = shared.HandoffLowConfidence
	}
	return out, nil
}

func (r *RouterResponder) escalateToOperator(lang shared.Language) Outcome {
	return Outcome{
		Text:          operatorMessage(lang),
		Type:          conversation.MessageTypeTicket,
		Confidence:    shared.NewConfidence(1),
		Escalate:      true,
		HandoffReason: shared.HandoffOperatorRequest,
	}
}

func priorMessages(session *conversation.Session) []conversation.Message {
	msgs := session.Messages()
	if len(msgs) == 0 {
		return nil
	}
	return msgs[:len(msgs)-1]
}

func operatorMessage(lang shared.Language) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return "Соединяю вас с оператором. Пожалуйста, подождите."
	case shared.LangEn.Code():
		return "Connecting you to an operator. Please wait a moment."
	case shared.LangCyr.Code():
		return "Сизни оператор билан боғлаяпман. Илтимос, бироз кутиб туринг."
	case shared.LangZh.Code():
		return "正在为您接通人工客服，请稍候。"
	default:
		return "Sizni operator bilan bog'layapman. Iltimos, biroz kuting."
	}
}
