package shared

import "strings"

// NormalizePhone strips formatting and returns E.164-ish digits for UZ numbers.
// Returns empty string when the input is not a plausible phone.
func NormalizePhone(raw string) string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return ""
	}
	var b strings.Builder
	for _, r := range raw {
		if r >= '0' && r <= '9' {
			b.WriteRune(r)
		}
	}
	digits := b.String()
	if len(digits) < 9 {
		return ""
	}
	if strings.HasPrefix(digits, "998") && len(digits) >= 12 {
		return digits
	}
	if len(digits) == 9 {
		return "998" + digits
	}
	if len(digits) >= 10 && len(digits) <= 15 {
		return digits
	}
	return ""
}
