package order

import (
	"regexp"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// These heuristics answer "is this message about the customer's own orders?"
// without a model. That matters in exactly the case where it is hardest to
// notice: when every LLM provider is down, routing falls back to keywords, and
// a customer asking "where are my orders" would otherwise be handed a
// knowledge-base article instead of their order list.

var (
	// orderListForms are plural or possessive-plural forms that mean "my
	// orders" on their own, with no second word needed.
	orderListForms = normalizeAll(
		"zakazlarim", "zakazlar", "buyurtmalarim", "buyurtmalar",
		"мои заказы", "мои товары", "мои посылки", "заказы", "посылки",
	)
	// orderPossessiveSingulars name one order without identifying it, so they
	// only signal a lookup when paired with a status word.
	orderPossessiveSingulars = normalizeAll(
		"buyurtmam", "zakazim", "tovarim", "posilkam",
		"мой заказ", "моя посылка",
	)
	// orderStatusWords ask about state or whereabouts.
	orderStatusWords = normalizeAll(
		"qayerda", "qayda", "qayer", "holat", "holati", "status", "kuzat",
		"korsat", "ko'rsat", "royxat", "ro'yxat",
		"где", "статус", "покажи", "отслеж",
	)
	// orderNouns are the things a customer calls an order. Unlike
	// orderNounWords it holds no pronouns, so pairing it with a status word
	// cannot be satisfied by "my" alone.
	orderNouns = normalizeAll(
		"zakaz", "buyurtma", "tovar", "posylk", "posilka", "order", "parcel",
		"заказ", "товар", "посылк",
	)
	// russianPossessives carry the "mine" that turns a bare noun into a
	// question about the customer's own orders.
	russianPossessives = normalizeAll("мои", "моя", "мой", "moi", "mani", "mening")
)

// followUpHint marks a message that continues the previous one rather than
// standing alone: "bu chi?", "unda?", "ham?". Matched on word boundaries so an
// ordinary word containing these letters does not qualify.
var followUpHint = regexp.MustCompile(`(^|\s)(chi|chu|dachi|ham|unda)(\s|\?|!|\.|,|$)`)

// IsListQuestion reports whether the message asks about the customer's orders
// in general. A message naming a specific parcel is not a list question: it
// wants that one order, not an inventory.
func IsListQuestion(text string) bool {
	if _, ok := shared.ExtractTrack(text); ok {
		return false
	}
	low := shared.NormalizeForMatch(text)
	if low == "" {
		return false
	}
	switch {
	case containsAny(low, orderListForms):
		return true
	case containsAny(low, allOrdersKeywords):
		return true
	case containsAny(low, orderPossessiveSingulars) && containsAny(low, orderStatusWords):
		return true
	case containsAny(low, russianPossessives) && containsAny(low, orderNouns):
		return true
	}
	return false
}

// IsLookupRequest reports whether the message is about the customer's own
// orders at all - a parcel number, a list question, a complaint that something
// has not arrived, or a status question naming an order.
//
// It deliberately requires a status word alongside the noun: "how do I place
// an order" mentions orders but is a knowledge-base question, not a lookup.
func IsLookupRequest(text string) bool {
	if _, ok := shared.ExtractTrack(text); ok {
		return true
	}
	if IsListQuestion(text) {
		return true
	}
	low := shared.NormalizeForMatch(text)
	if low == "" {
		return false
	}
	// "it hasn't arrived" is about a specific order even with nothing named.
	if containsAny(low, delayedKeywords) {
		return true
	}
	if !containsAny(low, orderNouns) {
		return false
	}
	return containsAny(low, orderStatusWords) ||
		containsAny(low, arrivalKeywords) ||
		(containsAny(low, arrivalAsks) && containsAny(low, arrivalVerbs))
}

// MergeFollowUp resolves a bare follow-up against the conversation.
//
// A customer who sends a tracking number and then just "bu chi?" ("and this
// one?") has left the parcel number in the previous turn. Looking the
// follow-up up on its own finds nothing and escalates to an operator, so the
// earlier message that carried a number is prepended to restore it.
//
// priorUserTexts is the customer's own earlier turns, oldest first.
func MergeFollowUp(text string, priorUserTexts []string) string {
	// A message that names its own parcel needs no help.
	if _, ok := shared.ExtractTrack(text); ok {
		return text
	}
	if !followUpHint.MatchString(shared.NormalizeForMatch(text)) {
		return text
	}
	for i := len(priorUserTexts) - 1; i >= 0; i-- {
		if _, ok := shared.ExtractTrack(priorUserTexts[i]); ok {
			return priorUserTexts[i] + " " + text
		}
	}
	return text
}
