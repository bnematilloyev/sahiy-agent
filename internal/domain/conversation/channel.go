package conversation

import "strings"

// Channel is the delivery channel a session belongs to (telegram, api, web...).
// It is a value object: normalized on construction and compared by value.
type Channel struct {
	value string
}

// Known channels.
var (
	ChannelAPI      = Channel{value: "api"}
	ChannelTelegram = Channel{value: "telegram"}
)

// NewChannel normalizes raw into a Channel, defaulting to "api" when blank.
func NewChannel(raw string) Channel {
	v := strings.ToLower(strings.TrimSpace(raw))
	if v == "" {
		return ChannelAPI
	}
	return Channel{value: v}
}

// String returns the channel name.
func (c Channel) String() string { return c.value }

// IsTelegram reports whether this is the Telegram channel, which has extra UX
// rules (identity gating, keyboards) in later phases.
func (c Channel) IsTelegram() bool { return c.value == ChannelTelegram.value }
