package shared

import "time"

// DomainEvent is something significant that happened in the domain. Aggregates
// record events as their state changes; the application layer pulls and
// dispatches them after the aggregate is persisted.
type DomainEvent interface {
	// EventName is a stable identifier for the event type.
	EventName() string
	// OccurredAt is when the event happened.
	OccurredAt() time.Time
}

// BaseEvent provides the OccurredAt timestamp for embedding into concrete events.
type BaseEvent struct {
	At time.Time
}

// OccurredAt implements part of DomainEvent.
func (b BaseEvent) OccurredAt() time.Time { return b.At }
