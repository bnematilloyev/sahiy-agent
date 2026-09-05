package feedback

import (
	"errors"
	"testing"
)

func TestNewRatingAcceptsTheOfferedScale(t *testing.T) {
	for stars := 1; stars <= 5; stars++ {
		got, err := NewRating("u1", "telegram", "sess", stars)
		if err != nil {
			t.Fatalf("NewRating(%d): %v", stars, err)
		}
		if got.Stars != stars {
			t.Errorf("Stars = %d, want %d", got.Stars, stars)
		}
	}
}

// An out-of-range value means the caller is wrong about the scale. Clamping it
// would quietly file a bogus 5 and corrupt the averages this table exists for.
func TestNewRatingRejectsOutOfRange(t *testing.T) {
	for _, stars := range []int{0, -1, 6, 100} {
		if _, err := NewRating("u1", "telegram", "sess", stars); !errors.Is(err, ErrStarsOutOfRange) {
			t.Errorf("NewRating(%d) error = %v, want ErrStarsOutOfRange", stars, err)
		}
	}
}

func TestNewRatingKeepsAttribution(t *testing.T) {
	got, err := NewRating("u1", "telegram", "sess-1", 4)
	if err != nil {
		t.Fatalf("NewRating: %v", err)
	}
	if got.UserID != "u1" || got.Channel != "telegram" || got.SessionID != "sess-1" {
		t.Errorf("attribution lost: %+v", got)
	}
}

// A rating given after the session rotated still counts; it simply has no
// session to join against.
func TestNewRatingAllowsMissingSession(t *testing.T) {
	got, err := NewRating("u1", "telegram", "", 3)
	if err != nil {
		t.Fatalf("NewRating without a session: %v", err)
	}
	if got.SessionID != "" {
		t.Errorf("SessionID = %q, want empty", got.SessionID)
	}
}
