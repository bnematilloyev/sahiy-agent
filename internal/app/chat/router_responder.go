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
// It receives the conversation history because a short follow-up ("bu chi?")
// only makes sense against the turn that named the parcel.
type OrderHandler interface {
	Respond(ctx context.Context, history []conversation.Message, query string, lang shared.Language, meta map[string]any) (Outcome, error)
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

// Respond implements Responder. It decides the route, dispatches to whoever
// handles it, then stamps the outcome with how the answer was produced so the
// caller can record the turn without re-deriving any of it.
func (r *RouterResponder) Respond(ctx context.Context, session *conversation.Session, text string, meta map[string]any) (Outcome, error) {
	history := priorMessages(session)
	decision := r.router.Decide(ctx, history, text, meta)
	r.log.Debug("route decided", "route", decision.Route.String(), "lang", decision.Language.Code())

	out, err := r.dispatch(ctx, session, history, text, meta, decision)
	if err != nil {
		return Outcome{}, err
	}
	out.Route = decision.Route.String()
	out.Language = decision.Language.Code()
	return out, nil
}

func (r *RouterResponder) dispatch(
	ctx context.Context,
	session *conversation.Session,
	history []conversation.Message,
	text string,
	meta map[string]any,
	decision routing.Decision,
) (Outcome, error) {
	if decision.Route.Equals(routing.RouteTicket) {
		if r.handlers.Support != nil {
			return r.handlers.Support.Respond(ctx, session, text, decision.Language, meta)
		}
		return r.escalateToOperator(decision.Language), nil
	}

	// An insult gets a civility reminder rather than a model call. Checked after
	// the ticket branch so an angry customer asking for an operator still gets one.
	if routing.IsProfanity(text) {
		return Outcome{
			Text:       civilityMessage(decision.Language),
			Type:       conversation.MessageTypeAuto,
			Confidence: shared.NewConfidence(1),
		}, nil
	}

	if decision.Route.Equals(routing.RouteChitchat) {
		ans, err := r.faq.Respond(ctx, nil, text, decision.Language)
		if err != nil {
			return Outcome{}, err
		}
		if ans.Degraded {
			// A greeting does not need an operator: answer it deterministically
			// rather than escalating or echoing a placeholder.
			return Outcome{
				Text:       greetingMessage(decision.Language),
				Type:       conversation.MessageTypeAuto,
				Confidence: shared.NewConfidence(chitchatConfidence),
				Degraded:   true,
			}, nil
		}
		return Outcome{
			Text:       ans.Text,
			Type:       conversation.MessageTypeAuto,
			Confidence: shared.NewConfidence(chitchatConfidence),
		}, nil
	}

	if decision.Route.Equals(routing.RouteAPI) && r.handlers.Order != nil {
		return r.handlers.Order.Respond(ctx, history, text, decision.Language, meta)
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
	// No model answered at all: hand off rather than show a placeholder.
	if ans.Degraded {
		r.log.Error("responder: degraded llm, escalating to operator")
		out := r.escalateToOperator(decision.Language)
		out.Degraded = true
		return out, nil
	}

	out := Outcome{
		Text:       ans.Text,
		Type:       conversation.MessageTypeAuto,
		Confidence: ans.Confidence,
	}
	if ans.Confidence.Below(r.escalationThreshold) {
		r.log.Info("responder: low confidence, escalating",
			"confidence", ans.Confidence.Float(), "threshold", r.escalationThreshold)
		out.Escalate = true
		out.HandoffReason = shared.HandoffLowConfidence
		out.Text = withOperatorNotice(ans.Text, decision.Language)
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
