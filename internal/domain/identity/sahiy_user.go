package identity

import (
	"regexp"
	"strings"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

var (
	sahiyUserIDPattern = regexp.MustCompile(`(?i)(?:user\s*id|userid|foydalanuvchi\s*id|sahiy\s*id|id)\s*[:#]?\s*(\d{3,10})\b`)
	fullDigits         = regexp.MustCompile(`^\d{3,8}$`)
)

// ExtractSahiyUserID parses a Sahiy DB user id from text (not Telegram user id).
func ExtractSahiyUserID(text string) int64 {
	stripped := strings.TrimSpace(text)
	if stripped == "" {
		return 0
	}
	if track, ok := shared.ExtractTrack(stripped); ok && track == stripped {
		return 0
	}
	if match := sahiyUserIDPattern.FindStringSubmatch(stripped); len(match) == 2 {
		return parsePositiveInt(match[1])
	}
	if fullDigits.MatchString(stripped) {
		return parsePositiveInt(stripped)
	}
	return 0
}

// IsIdentityOnlyMessage reports whether text is only a phone or Sahiy id submission.
func IsIdentityOnlyMessage(text string) bool {
	stripped := strings.TrimSpace(text)
	if stripped == "" {
		return false
	}
	if sid := ExtractSahiyUserID(stripped); sid != 0 {
		if intToString(sid) == stripped {
			return true
		}
		if sahiyUserIDPattern.MatchString(stripped) {
			return true
		}
	}
	phone := ExtractRegistrationPhone(stripped)
	if phone == "" {
		return false
	}
	compact := strings.ReplaceAll(strings.ToLower(stripped), " ", "")
	switch compact {
	case phone, stripped, "+" + phone, "telefon" + phone, "tel" + phone:
		return true
	default:
		return false
	}
}

// RequiresCustomerIdentity reports whether a channel must verify Sahiy account first.
func RequiresCustomerIdentity(channel string) bool {
	return channel == "telegram"
}

func parsePositiveInt(s string) int64 {
	var n int64
	for _, r := range s {
		if r < '0' || r > '9' {
			return 0
		}
		n = n*10 + int64(r-'0')
	}
	return n
}

func intToString(n int64) string {
	if n <= 0 {
		return ""
	}
	var digits [20]byte
	i := len(digits)
	for n > 0 {
		i--
		digits[i] = byte('0' + n%10)
		n /= 10
	}
	return string(digits[i:])
}
