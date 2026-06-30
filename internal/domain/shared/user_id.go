// Package shared is the DDD shared kernel: value objects and primitives that are
// meaningful across more than one bounded context (conversation, support,
// knowledge). Keeping them here avoids duplication while still preventing the
// contexts from depending on each other.
package shared

import (
	"errors"
	"strings"
)

// ErrEmptyUserID is returned when constructing a UserID from blank input.
var ErrEmptyUserID = errors.New("user id must not be empty")

// UserID is a value object identifying the end user across contexts. It is
// always non-empty and compared by value.
type UserID struct {
	value string
}

// NewUserID validates and constructs a UserID.
func NewUserID(raw string) (UserID, error) {
	v := strings.TrimSpace(raw)
	if v == "" {
		return UserID{}, ErrEmptyUserID
	}
	return UserID{value: v}, nil
}

// String returns the raw identifier.
func (u UserID) String() string { return u.value }

// IsZero reports whether the value object is uninitialized.
func (u UserID) IsZero() bool { return u.value == "" }
