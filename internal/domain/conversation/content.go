package conversation

import "strings"

// Content is a non-empty message body value object. Construction trims
// surrounding whitespace and rejects empty input, so an invalid Content can
// never enter the domain.
type Content struct {
	value string
}

// NewContent validates and constructs message content.
func NewContent(raw string) (Content, error) {
	v := strings.TrimSpace(raw)
	if v == "" {
		return Content{}, ErrEmptyContent
	}
	return Content{value: v}, nil
}

// contentFromStore reconstitutes content from persistence without validation,
// tolerating any historical rows.
func contentFromStore(raw string) Content { return Content{value: raw} }

// String returns the message text.
func (c Content) String() string { return c.value }
