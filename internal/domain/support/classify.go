package support

import "strings"

var complaintKeywords = []string{
	"shikoyat", "norozi", "yomon", "buzilgan", "singan", "yo'qolgan", "kechik",
	"жалоб", "сломан", "complaint", "broken", "damaged", "lost", "late",
}

func containsComplaintKeyword(text string) bool {
	low := strings.ToLower(text)
	for _, kw := range complaintKeywords {
		if strings.Contains(low, kw) {
			return true
		}
	}
	return false
}

// InferTicketType classifies a support request from message keywords.
func InferTicketType(text string) Type {
	if containsComplaintKeyword(text) {
		return NewType("complaint")
	}
	return NewType("operator")
}
