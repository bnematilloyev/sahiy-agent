package ai

import (
	"encoding/json"
	"strings"
)

// answerContract is appended to every customer-facing system prompt. It makes
// the model report how well it could actually answer, so the application can
// escalate instead of presenting a confident-sounding guess.
//
// Confidence is about the ANSWER, not about retrieval: a perfect knowledge-base
// match that does not cover the question must still score low.
const answerContract = `
Respond with ONLY a compact JSON object, no prose and no code fences:
{"answer":"<your reply to the customer>","confidence":<0.0-1.0>}

confidence rules - be strict and honest, an unsure answer is escalated to a
human operator, which is always better than a wrong one:
- 0.9-1.0: the information needed is fully present and you are certain.
- 0.6-0.8: you can answer, but some detail is missing or ambiguous.
- 0.0-0.4: the information is not available to you, the question needs
  account-specific data you were not given, or you would have to guess.
Never invent prices, dates, delivery times, order states or policies. If you
do not know, say so in "answer" and score below 0.4.`

// WithAnswerContract appends the JSON answer contract to a system prompt.
func WithAnswerContract(system string) string {
	return strings.TrimSpace(system) + "\n" + answerContract
}

// ParsedAnswer is a model reply decoded from the answer contract.
type ParsedAnswer struct {
	Text       string
	Confidence float64
}

// fallbackConfidence is assigned when the model ignored the JSON contract. It
// sits deliberately below the default escalation threshold: an unparseable
// reply is a reply we cannot vouch for.
const fallbackConfidence = 0.3

// ParseAnswer decodes a model reply that follows the answer contract. When the
// model answered in plain prose instead, the raw text is kept and scored with
// fallbackConfidence so the caller escalates rather than trusting it blindly.
// The bool reports whether the contract was honoured.
func ParseAnswer(raw string) (ParsedAnswer, bool) {
	obj, ok := ExtractJSONObject(raw)
	if !ok {
		return ParsedAnswer{Text: strings.TrimSpace(raw), Confidence: fallbackConfidence}, false
	}

	var decoded struct {
		Answer     string   `json:"answer"`
		Confidence *float64 `json:"confidence"`
	}
	if err := json.Unmarshal([]byte(obj), &decoded); err != nil {
		return ParsedAnswer{Text: strings.TrimSpace(raw), Confidence: fallbackConfidence}, false
	}

	answer := strings.TrimSpace(decoded.Answer)
	if answer == "" || decoded.Confidence == nil {
		return ParsedAnswer{Text: strings.TrimSpace(raw), Confidence: fallbackConfidence}, false
	}

	confidence := *decoded.Confidence
	switch {
	case confidence < 0:
		confidence = 0
	case confidence > 1:
		confidence = 1
	}
	return ParsedAnswer{Text: answer, Confidence: confidence}, true
}

// ExtractJSONObject returns the outermost {...} span of a model reply,
// tolerating surrounding prose or code fences.
func ExtractJSONObject(raw string) (string, bool) {
	start := strings.IndexByte(raw, '{')
	end := strings.LastIndexByte(raw, '}')
	if start < 0 || end <= start {
		return "", false
	}
	return raw[start : end+1], true
}
