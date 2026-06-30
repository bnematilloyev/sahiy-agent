// Package eventlog provides a logging implementation of the application's
// EventPublisher. It records domain events to the structured logger; a real
// message bus can replace it later without touching the use case.
package eventlog

import (
	"context"
	"log/slog"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// Publisher logs domain events.
type Publisher struct {
	log *slog.Logger
}

// New constructs a logging publisher.
func New(log *slog.Logger) *Publisher { return &Publisher{log: log} }

// Publish logs each event at debug level.
func (p *Publisher) Publish(_ context.Context, events []shared.DomainEvent) {
	for _, e := range events {
		p.log.Debug("domain event", "event", e.EventName(), "at", e.OccurredAt())
	}
}
