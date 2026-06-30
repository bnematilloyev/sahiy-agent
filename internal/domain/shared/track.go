package shared

import "regexp"

// trackPattern matches logistics track numbers: 9–24 chars, alphanumeric, with
// at least one digit (e.g. "SF1234567890", "780123456789").
var trackPattern = regexp.MustCompile(`\b[A-Za-z]{0,4}\d[A-Za-z0-9]{7,23}\b`)

// ExtractTrack returns the first track-number-like token found in text.
func ExtractTrack(text string) (string, bool) {
	m := trackPattern.FindString(text)
	if m == "" {
		return "", false
	}
	return m, true
}
