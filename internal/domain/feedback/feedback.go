// Package feedback is the bounded context for what the assistant learns about
// its own answers: customer star ratings and per-turn quality telemetry.
package feedback

import (
	"context"
	"errors"
	"time"
)

// ErrStarsOutOfRange rejects a rating outside the 1-5 scale the prompt offers.
var ErrStarsOutOfRange = errors.New("feedback: stars must be between 1 and 5")

// Rating is one customer's verdict on a conversation.
type Rating struct {
	UserID    string
	Channel   string
	SessionID string
	Stars     int
}

// NewRating validates a star rating. An out-of-range value is rejected rather
// than clamped: a 7 means the caller is wrong about the scale, and silently
// storing 5 would corrupt the very numbers this table exists to report.
func NewRating(userID, channel, sessionID string, stars int) (Rating, error) {
	if stars < 1 || stars > 5 {
		return Rating{}, ErrStarsOutOfRange
	}
	return Rating{UserID: userID, Channel: channel, SessionID: sessionID, Stars: stars}, nil
}

// Turn is what the assistant did for one customer message.
type Turn struct {
	SessionID     string
	Channel       string
	Route         string
	ReplyLanguage string
	Confidence    float64
	Escalated     bool
	HandoffReason string
	// Degraded reports that no real model answered - the rules fallback did.
	// It separates "the assistant was unsure" from "the assistant was blind",
	// which look identical in a confidence figure alone.
	Degraded bool
	Duration time.Duration
}

// Recorder persists the learning-loop records.
//
// Recording is best-effort and must never affect the customer's reply, so the
// methods take no error return; implementations handle their own failures.
type Recorder interface {
	RecordRating(ctx context.Context, r Rating)
	RecordTurn(ctx context.Context, t Turn)
}
