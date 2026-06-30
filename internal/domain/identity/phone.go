package identity

import (
	"regexp"
	"strings"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

var phoneInTextPattern = regexp.MustCompile(`\+?[\d][\d\s\-()]{8,14}\d`)

// ValidateUzbekPhone returns normalized 998XXXXXXXXX or empty when invalid.
func ValidateUzbekPhone(phone string) string {
	phone = strings.TrimSpace(phone)
	if phone == "" {
		return ""
	}
	normalized := shared.NormalizePhone(phone)
	digits := digitsOnly(normalized)
	if !isUzbekMobileDigits(digits) {
		return ""
	}
	return normalized
}

// PhoneSearchCandidates returns API search variants for a phone string.
func PhoneSearchCandidates(phone string) []string {
	stripped := strings.TrimSpace(phone)
	if stripped == "" {
		return nil
	}

	seen := make(map[string]struct{})
	add := func(v string) {
		v = strings.TrimSpace(v)
		if v == "" {
			return
		}
		if _, ok := seen[v]; !ok {
			seen[v] = struct{}{}
		}
	}
	out := func() []string {
		result := make([]string, 0, len(seen))
		for v := range seen {
			result = append(result, v)
		}
		return result
	}

	if standard := ValidateUzbekPhone(stripped); standard != "" {
		add(standard)
	}

	digits := digitsOnly(stripped)
	if digits == "" {
		return out()
	}
	if track, ok := shared.ExtractTrack(digits); ok && track == digits {
		return out()
	}

	if len(digits) >= 7 && len(digits) <= 12 {
		add(digits)
		if !strings.HasPrefix(digits, "998") {
			add("998" + digits)
		}
	}

	if fromText := extractPhoneFromText(stripped); fromText != "" {
		add(fromText)
	}

	return out()
}

// ExtractRegistrationPhone extracts a plausible phone from free-form text.
func ExtractRegistrationPhone(text string) string {
	stripped := strings.TrimSpace(text)
	if stripped == "" {
		return ""
	}
	if ExtractSahiyUserID(stripped) != 0 && fullDigits.MatchString(stripped) {
		return ""
	}
	candidates := PhoneSearchCandidates(stripped)
	if len(candidates) == 0 {
		return ""
	}
	return candidates[0]
}

// ResolveContactPhone normalizes a Telegram contact phone number.
func ResolveContactPhone(raw string) string {
	return ExtractRegistrationPhone(raw)
}

func isUzbekMobileDigits(digits string) bool {
	if len(digits) == 12 && strings.HasPrefix(digits, "998") {
		return digits[3] == '9'
	}
	if len(digits) == 9 && strings.HasPrefix(digits, "9") {
		return true
	}
	return false
}

func digitsOnly(value string) string {
	var b strings.Builder
	for _, r := range value {
		if r >= '0' && r <= '9' {
			b.WriteRune(r)
		}
	}
	return b.String()
}

func extractPhoneFromText(text string) string {
	match := phoneInTextPattern.FindString(text)
	if match == "" {
		return ""
	}
	return ValidateUzbekPhone(match)
}
