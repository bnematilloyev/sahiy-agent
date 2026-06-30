package routing

import (
	"strings"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// operatorPhrases are substrings that signal the user wants a human operator.
var operatorPhrases = []string{
	"operator", "operatorga", "operator bilan", "jonli", "jonli yordam",
	"menejer", "manager", "human", "real odam", "odam bilan", "tirik",
	"оператор", "оператора", "менеджер", "человек", "живой",
}

// chitchatPhrases are short social messages with no informational intent.
var chitchatPhrases = []string{
	"salom", "assalom", "assalomu", "rahmat", "raxmat", "xayr", "ok", "okay",
	"yaxshi", "zo'r", "hello", "hi", "hey", "thanks", "thank you", "bye",
	"привет", "здравствуйте", "спасибо", "пока", "хорошо",
}

// ExtractTrack delegates to the shared kernel track parser.
func ExtractTrack(text string) (string, bool) {
	return shared.ExtractTrack(text)
}

// IsOperatorRequest reports whether the user explicitly asks for a human.
func IsOperatorRequest(text string) bool {
	low := strings.ToLower(text)
	for _, p := range operatorPhrases {
		if strings.Contains(low, p) {
			return true
		}
	}
	return false
}

// IsChitchat reports whether the message is a short social greeting/thanks with
// no informational request.
func IsChitchat(text string) bool {
	low := strings.TrimSpace(strings.ToLower(text))
	if low == "" {
		return false
	}
	// Only treat very short messages as chitchat to avoid swallowing questions.
	if len(strings.Fields(low)) > 4 {
		return false
	}
	for _, p := range chitchatPhrases {
		if low == p || strings.HasPrefix(low, p) {
			return true
		}
	}
	return false
}

// FallbackRoute is the deterministic keyword-based router used when the LLM is
// unavailable or to reconcile its output. Precedence: operator > track > chitchat
// > faq.
func FallbackRoute(text string) Route {
	switch {
	case IsOperatorRequest(text):
		return RouteTicket
	case func() bool { _, ok := ExtractTrack(text); return ok }():
		return RouteAPI
	case IsChitchat(text):
		return RouteChitchat
	default:
		return RouteFAQ
	}
}
