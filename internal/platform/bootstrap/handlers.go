package bootstrap

import (
	"context"
	"log/slog"

	appcatalog "github.com/sahiy-backend/sahiy-agent/internal/app/catalog"
	"github.com/sahiy-backend/sahiy-agent/internal/app/chat"
	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
	apporder "github.com/sahiy-backend/sahiy-agent/internal/app/order"
	apppickup "github.com/sahiy-backend/sahiy-agent/internal/app/pickup"
	appsupport "github.com/sahiy-backend/sahiy-agent/internal/app/support"
	"github.com/sahiy-backend/sahiy-agent/internal/config"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/conversation"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
	"github.com/sahiy-backend/sahiy-agent/internal/infra/exchange"
	"github.com/sahiy-backend/sahiy-agent/internal/infra/persistence/postgres"
	sahiyinfra "github.com/sahiy-backend/sahiy-agent/internal/infra/sahiy"
	"github.com/sahiy-backend/sahiy-agent/internal/channel/telegram"
)

func buildHandlers(cfg *config.Config, stack *sahiyinfra.ServiceStack, ticketRepo *postgres.TicketRepository, completer ai.Completer, log *slog.Logger) (chat.Handlers, telegram.CallbackServices) {
	var handlers chat.Handlers
	var callbacks telegram.CallbackServices

	if stack != nil {
		rates := exchange.NewProvider(cfg.Exchange, cfg.AI.Timeout)
		productAPI := sahiyinfra.NewProductSearchAPI(stack.Client, cfg.Sahiy.GoodsDeeplinkBase, cfg.Sahiy.SearchDeeplinkBase, cfg.Sahiy.ProductSearchPage, cfg.Sahiy.ProductSearchSort)
		categoriesAPI := sahiyinfra.NewCategoriesAPI(stack.Client, cfg.Sahiy.CategoriesCacheTTL)
		pickupAPI := sahiyinfra.NewPickupPointsAPI(stack.Client, cfg.Sahiy.PickupCacheTTL)

		orderSvc := apporder.New(stack.CustomerAPI, completer, cfg.AI.OrderMaxTokens, log)
		productSvc := appcatalog.NewProductSearchService(productAPI, rates, log)
		categorySvc := appcatalog.NewCategoryService(categoriesAPI, cfg.Sahiy.CategoryDeeplinkBase, log)
		pickupSvc := apppickup.New(pickupAPI, log)

		handlers.Order = &orderHandlerAdapter{svc: orderSvc}
		handlers.ProductSearch = &productSearchAdapter{svc: productSvc}
		handlers.Category = &categoryAdapter{svc: categorySvc}
		handlers.Pickup = &pickupAdapter{svc: pickupSvc}
		callbacks = telegram.CallbackServices{
			Pickup:        pickupSvc,
			Category:      categorySvc,
			ProductSearch: productSvc,
		}
		log.Info("sahiy handlers enabled", "base_url", cfg.Sahiy.BaseURL)
	} else {
		log.Info("sahiy handlers disabled (no service user), api/catalog/pickup routes fall back to faq")
	}

	supportSvc := appsupport.New(ticketRepo, log)
	handlers.Support = &supportHandlerAdapter{svc: supportSvc}
	return handlers, callbacks
}

type orderHandlerAdapter struct {
	svc *apporder.Service
}

func (a *orderHandlerAdapter) Respond(ctx context.Context, query string, lang shared.Language, meta map[string]any) (chat.Outcome, error) {
	res, err := a.svc.Respond(ctx, query, lang, meta)
	if err != nil {
		return chat.Outcome{}, err
	}
	return handlerResultToOutcome(res.Text, res.Confidence, res.Escalate, res.HandoffReason, nil), nil
}

type supportHandlerAdapter struct {
	svc *appsupport.Service
}

func (a *supportHandlerAdapter) Respond(ctx context.Context, session *conversation.Session, text string, lang shared.Language, meta map[string]any) (chat.Outcome, error) {
	res, err := a.svc.Respond(ctx, session, text, lang, meta)
	if err != nil {
		return chat.Outcome{}, err
	}
	return handlerResultToOutcome(res.Text, res.Confidence, res.Escalate, res.HandoffReason, res.TicketID), nil
}

type productSearchAdapter struct {
	svc *appcatalog.ProductSearchService
}

func (a *productSearchAdapter) Respond(ctx context.Context, query string, lang shared.Language) (chat.Outcome, error) {
	res, err := a.svc.Respond(ctx, query, lang)
	if err != nil {
		return chat.Outcome{}, err
	}
	return catalogResultToOutcome(res), nil
}

type categoryAdapter struct {
	svc *appcatalog.CategoryService
}

func (a *categoryAdapter) Respond(ctx context.Context, query string, lang shared.Language) (chat.Outcome, error) {
	res, err := a.svc.Respond(ctx, query, lang)
	if err != nil {
		return chat.Outcome{}, err
	}
	return catalogResultToOutcome(res), nil
}

type pickupAdapter struct {
	svc *apppickup.Service
}

func (a *pickupAdapter) Respond(ctx context.Context, query string, lang shared.Language) (chat.Outcome, error) {
	res, err := a.svc.Respond(ctx, query, lang)
	if err != nil {
		return chat.Outcome{}, err
	}
	return chat.Outcome{
		Text:         res.Text,
		Type:         conversation.MessageTypeAuto,
		Confidence:   res.Confidence,
		ChannelExtra: res.ChannelExtra,
	}, nil
}

func handlerResultToOutcome(text string, conf shared.Confidence, escalate bool, handoff shared.HandoffReason, ticketID *string) chat.Outcome {
	msgType := conversation.MessageTypeAuto
	if escalate {
		msgType = conversation.MessageTypeTicket
	}
	return chat.Outcome{
		Text:          text,
		Type:          msgType,
		Confidence:    conf,
		Escalate:      escalate,
		HandoffReason: handoff,
		TicketID:      ticketID,
	}
}

func catalogResultToOutcome(res appcatalog.Result) chat.Outcome {
	return chat.Outcome{
		Text:         res.Text,
		Type:         conversation.MessageTypeAuto,
		Confidence:   res.Confidence,
		ChannelExtra: res.ChannelExtra,
	}
}
