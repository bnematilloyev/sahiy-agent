// Package support is the application service for operator handoff tickets.
package support

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/conversation"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
	domainsupport "github.com/sahiy-backend/sahiy-agent/internal/domain/support"
)

// Result is the support handler outcome for one turn.
type Result struct {
	Text          string
	Confidence    shared.Confidence
	Escalate      bool
	HandoffReason shared.HandoffReason
	TicketID      *string
}

// Service creates and tracks support tickets.
type Service struct {
	tickets domainsupport.Repository
	log     *slog.Logger
}

// New constructs the support service.
func New(tickets domainsupport.Repository, log *slog.Logger) *Service {
	return &Service{tickets: tickets, log: log}
}

// Respond opens or reminds about a support ticket for the session.
func (s *Service) Respond(ctx context.Context, session *conversation.Session, text string, lang shared.Language, _ map[string]any) (Result, error) {
	open, err := s.tickets.FindOpenBySession(ctx, session.ID())
	if err != nil {
		return Result{}, fmt.Errorf("support: find open ticket: %w", err)
	}
	if open != nil {
		id := open.ID().String()
		return Result{
			Text:          ticketReminderMessage(lang, id),
			Confidence:    shared.NewConfidence(1),
			Escalate:      true,
			HandoffReason: shared.HandoffOperatorRequest,
			TicketID:      &id,
		}, nil
	}

	ticket := domainsupport.Open(session.ID(), session.UserID(), domainsupport.InferTicketType(text))
	if err := s.tickets.Save(ctx, ticket); err != nil {
		return Result{}, fmt.Errorf("support: save ticket: %w", err)
	}
	id := ticket.ID().String()
	s.log.Info("support ticket opened", "ticket_id", id, "session_id", session.ID().String())
	return Result{
		Text:          ticketAckMessage(lang, id),
		Confidence:    shared.NewConfidence(1),
		Escalate:      true,
		HandoffReason: shared.HandoffOperatorRequest,
		TicketID:      &id,
	}, nil
}

func ticketAckMessage(lang shared.Language, ticketID string) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return fmt.Sprintf("Ваш запрос принят. Номер обращения: %s. Оператор скоро ответит.", ticketID)
	case shared.LangEn.Code():
		return fmt.Sprintf("Your request has been received. Ticket #%s. An operator will respond shortly.", ticketID)
	case shared.LangCyr.Code():
		return fmt.Sprintf("Сўровингиз қабул қилинди. Мурожаат рақами: %s. Оператор тез орада жавоб беради.", ticketID)
	case shared.LangZh.Code():
		return fmt.Sprintf("您的请求已受理，工单号：%s。客服人员将尽快回复。", ticketID)
	default:
		return fmt.Sprintf("So'rovingiz qabul qilindi. Murojaat raqami: %s. Operator tez orada javob beradi.", ticketID)
	}
}

func ticketReminderMessage(lang shared.Language, ticketID string) string {
	switch lang.Code() {
	case shared.LangRu.Code():
		return fmt.Sprintf("У вас уже есть открытое обращение #%s. Оператор скоро ответит.", ticketID)
	case shared.LangEn.Code():
		return fmt.Sprintf("You already have an open ticket #%s. An operator will respond shortly.", ticketID)
	case shared.LangCyr.Code():
		return fmt.Sprintf("Сизда аллақачон #%s рақамли мурожаат бор. Оператор тез орада жавоб беради.", ticketID)
	case shared.LangZh.Code():
		return fmt.Sprintf("您已有未关闭的工单 #%s，客服人员将尽快回复。", ticketID)
	default:
		return fmt.Sprintf("Sizda ochiq murojaat #%s bor. Operator tez orada javob beradi.", ticketID)
	}
}
