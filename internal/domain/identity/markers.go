// Package identity holds customer identification rules shared by chat and order flows.
package identity

import (
	"strconv"
	"strings"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/conversation"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

const (
	// PhoneMessagePrefix marks a verified phone persisted in session history.
	PhoneMessagePrefix = "PHONE:"
	// SahiyUserMessagePrefix marks a verified Sahiy user id in session history.
	SahiyUserMessagePrefix = "SAHIY_USER:"
)

// CustomerIdentity is the verified customer context recovered from metadata or session.
type CustomerIdentity struct {
	Phone       string
	SahiyUserID int64
}

// HasSahiyUser reports whether a Sahiy account id is known.
func (c CustomerIdentity) HasSahiyUser() bool { return c.SahiyUserID > 0 }

// FromMetadata reads identity fields from transport metadata.
func FromMetadata(meta map[string]any) CustomerIdentity {
	if meta == nil {
		return CustomerIdentity{}
	}
	var out CustomerIdentity
	if raw, ok := meta["verified_phone"].(string); ok {
		out.Phone = shared.NormalizePhone(raw)
	}
	if uid, ok := metaInt64(meta["sahiy_user_id"]); ok {
		out.SahiyUserID = uid
	}
	return out
}

// FromMessages scans session messages for the latest PHONE:/SAHIY_USER: markers.
func FromMessages(msgs []conversation.Message) CustomerIdentity {
	var out CustomerIdentity
	for _, m := range msgs {
		if m.Role() != conversation.RoleUser {
			continue
		}
		content := m.Content().String()
		switch {
		case strings.HasPrefix(content, PhoneMessagePrefix):
			out.Phone = shared.NormalizePhone(content[len(PhoneMessagePrefix):])
		case strings.HasPrefix(content, SahiyUserMessagePrefix):
			if uid, err := strconv.ParseInt(strings.TrimSpace(content[len(SahiyUserMessagePrefix):]), 10, 64); err == nil {
				out.SahiyUserID = uid
			}
		}
	}
	return out
}

// EnrichMetadata merges stored identity into metadata when callers did not supply it.
func EnrichMetadata(meta map[string]any, stored CustomerIdentity) {
	if meta == nil {
		return
	}
	if stored.Phone != "" {
		if raw, ok := meta["verified_phone"].(string); !ok || strings.TrimSpace(raw) == "" {
			meta["verified_phone"] = stored.Phone
		}
	}
	if stored.SahiyUserID > 0 {
		if _, ok := meta["sahiy_user_id"]; !ok {
			meta["sahiy_user_id"] = stored.SahiyUserID
		}
	}
}

func metaInt64(v any) (int64, bool) {
	switch n := v.(type) {
	case int64:
		return n, n > 0
	case int:
		return int64(n), n > 0
	case float64:
		return int64(n), n > 0
	case string:
		uid, err := strconv.ParseInt(strings.TrimSpace(n), 10, 64)
		return uid, err == nil && uid > 0
	default:
		return 0, false
	}
}
