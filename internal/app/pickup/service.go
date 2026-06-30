// Package pickup is the application service for pickup point inquiries.
package pickup

import (
	"context"
	"log/slog"

	domainpickup "github.com/sahiy-backend/sahiy-agent/internal/domain/pickup"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// PointsFetcher loads pickup points.
type PointsFetcher interface {
	All(ctx context.Context) ([]domainpickup.Point, error)
}

// Result is a pickup handler outcome.
type Result struct {
	Text         string
	Confidence   shared.Confidence
	ChannelExtra map[string]any
}

// Service answers pickup point queries.
type Service struct {
	points PointsFetcher
	log    *slog.Logger
}

// New constructs the pickup service.
func New(points PointsFetcher, log *slog.Logger) *Service {
	return &Service{points: points, log: log}
}

// RespondCallback handles Telegram pp_ inline callbacks.
func (s *Service) RespondCallback(ctx context.Context, kind string, value int, lang shared.Language) (Result, error) {
	points, err := s.points.All(ctx)
	if err != nil {
		return Result{Text: domainpickup.FormatOverview(nil, lang), Confidence: shared.NewConfidence(0.3)}, nil
	}
	var filtered []domainpickup.Point
	switch kind {
	case "r":
		filtered = domainpickup.FilterByRegionID(int64(value), points)
	case "t":
		filtered = domainpickup.FilterByType(value, points)
	}
	if len(filtered) == 0 {
		return Result{Text: domainpickup.FormatOverview(points, lang), Confidence: shared.NewConfidence(0.5)}, nil
	}
	return Result{
		Text:       domainpickup.FormatRegionList(filtered, lang),
		Confidence: shared.NewConfidence(0.9),
	}, nil
}

func (s *Service) Respond(ctx context.Context, query string, lang shared.Language) (Result, error) {
	points, err := s.points.All(ctx)
	if err != nil {
		s.log.Warn("pickup: fetch failed", "error", err)
		return Result{
			Text:       domainpickup.FormatOverview(nil, lang),
			Confidence: shared.NewConfidence(0.3),
		}, nil
	}
	if len(points) == 0 {
		return Result{
			Text:       domainpickup.FormatOverview(nil, lang),
			Confidence: shared.NewConfidence(0.5),
		}, nil
	}
	if local := domainpickup.FilterByLocationQuery(query, points); len(local) > 0 {
		return Result{
			Text:       domainpickup.FormatRegionList(local, lang),
			Confidence: shared.NewConfidence(0.9),
		}, nil
	}
	keyboard := domainpickup.BuildRegionKeyboard(points)
	return Result{
		Text:         domainpickup.OverviewHeader(lang, len(points)),
		Confidence:   shared.NewConfidence(0.9),
		ChannelExtra: domainpickup.PickupInlineExtra(keyboard, len(points)),
	}, nil
}
