package ai

import (
	"context"
	"testing"
)

func TestSessionIDRoundTrip(t *testing.T) {
	ctx := WithSessionID(context.Background(), "abc-123")
	if got := SessionIDFrom(ctx); got != "abc-123" {
		t.Fatalf("SessionIDFrom = %q, want abc-123", got)
	}
}

func TestSessionIDAbsent(t *testing.T) {
	if got := SessionIDFrom(context.Background()); got != "" {
		t.Fatalf("SessionIDFrom on a bare context = %q, want empty", got)
	}
}

func TestWithSessionIDIgnoresEmpty(t *testing.T) {
	// An empty id must not overwrite one already on the context, and must not
	// store an empty value that later reads would report as "present".
	ctx := WithSessionID(context.Background(), "abc-123")
	ctx = WithSessionID(ctx, "")
	if got := SessionIDFrom(ctx); got != "abc-123" {
		t.Fatalf("SessionIDFrom after empty WithSessionID = %q, want abc-123", got)
	}
}
