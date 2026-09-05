package routing

import (
	"strings"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/order"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// Keyword rules are written in Uzbek Latin only. Input and rules both go
// through shared.NormalizeForMatch, so Cyrillic ("оператор") and typographic
// apostrophes ("bo‘lsa") match the same rule without duplicate entries.

// operatorPhrases are substrings that signal the user wants a human operator.
var operatorPhrases = normalizeAll(
	"operator", "operatorga", "operator bilan", "jonli", "jonli yordam",
	"menejer", "menedjer", "manager", "human", "real odam", "odam bilan", "tirik",
	"chelovek", "jivoy",
)

// chitchatPhrases are short social messages with no informational intent.
var chitchatPhrases = normalizeAll(
	"salom", "assalom", "assalomu", "rahmat", "raxmat", "xayr", "ok", "okay",
	"yaxshi", "zo'r", "hello", "hi", "hey", "thanks", "thank you", "bye",
	"privet", "zdravstvuyte", "spasibo", "poka", "xorosho",
)

// profanityWords are insults that should get a civility reminder instead of an
// answer. Ported from the Python service; single words are matched on word
// boundaries so ordinary text is not flagged by accident.
// TODO: "dala" is carried over from Python but is an ordinary Uzbek word
// ("field"); it is kept for parity and should be reviewed by the support team.
var profanityWords = normalizeAll(
	"eshak", "ahmoq", "sharmanda", "dala", "itdan tarqagan",
)

// companyTopicWords turn a message that mentions Sahiy into a "what is this
// company" question.
var companyTopicWords = normalizeAll(
	"kompaniya", "nima", "qanday", "kim", "haqida", "do'kon", "dokon",
)

func normalizeAll(phrases ...string) []string {
	out := make([]string, len(phrases))
	for i, p := range phrases {
		out[i] = shared.NormalizeForMatch(p)
	}
	return out
}

// ExtractTrack delegates to the shared kernel track parser.
func ExtractTrack(text string) (string, bool) {
	return shared.ExtractTrack(text)
}

// IsOperatorRequest reports whether the user explicitly asks for a human.
func IsOperatorRequest(text string) bool {
	return containsAny(shared.NormalizeForMatch(text), operatorPhrases)
}

// IsChitchat reports whether the message is a short social greeting/thanks with
// no informational request.
func IsChitchat(text string) bool {
	low := shared.NormalizeForMatch(text)
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

// IsProfanity reports whether the message contains an insult from the known list.
func IsProfanity(text string) bool {
	low := shared.NormalizeForMatch(text)
	for _, word := range profanityWords {
		if strings.ContainsRune(word, ' ') {
			if strings.Contains(low, word) {
				return true
			}
			continue
		}
		if containsWord(low, word) {
			return true
		}
	}
	return false
}

// IsCompanyQuestion reports whether the user is asking what Sahiy is, rather
// than asking about their own order.
func IsCompanyQuestion(text string) bool {
	low := shared.NormalizeForMatch(text)
	if !strings.Contains(low, "sahiy") {
		return false
	}
	return containsAny(low, companyTopicWords)
}

func containsAny(text string, phrases []string) bool {
	for _, p := range phrases {
		if strings.Contains(text, p) {
			return true
		}
	}
	return false
}

// containsWord reports whether word appears in text as a whole word, so "dala"
// does not match inside "dalada".
func containsWord(text, word string) bool {
	for _, field := range strings.FieldsFunc(text, func(r rune) bool {
		return !isWordRune(r)
	}) {
		if field == word {
			return true
		}
	}
	return false
}

func isWordRune(r rune) bool {
	return r == '\'' || r == '-' ||
		(r >= 'a' && r <= 'z') || (r >= '0' && r <= '9')
}

// FallbackRoute is the deterministic keyword-based router used when the LLM is
// unavailable or to reconcile its output. Precedence: operator > order >
// chitchat > faq.
//
// The order test is order.IsLookupRequest rather than a bare track match:
// without it, a customer asking "where are my orders" during an LLM outage is
// routed to the knowledge base and answered with an article instead of their
// own data. Routing may reach into the order context this way because it is
// the component deciding which context handles the message.
func FallbackRoute(text string) Route {
	switch {
	case IsOperatorRequest(text):
		return RouteTicket
	case order.IsLookupRequest(text):
		return RouteAPI
	case IsChitchat(text):
		return RouteChitchat
	default:
		return RouteFAQ
	}
}
