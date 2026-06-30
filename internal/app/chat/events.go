package chat

import (
	"context"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// EventPublisher dispatches domain events recorded by aggregates after they are
// persisted. A logging implementation is enough for now; a real bus can be
// swapped in later without changing the use case.
type EventPublisher interface {
	Publish(ctx context.Context, events []shared.DomainEvent)
}

// NoopEventPublisher discards events. Useful in tests.
type NoopEventPublisher struct{}

// Publish implements EventPublisher.
func (NoopEventPublisher) Publish(context.Context, []shared.DomainEvent) {}
