// Package knowledge is the bounded context for the FAQ knowledge base used by
// retrieval-augmented answering. Its aggregate root is FAQEntry.
package knowledge

import "github.com/sahiy-backend/sahiy-agent/internal/domain/shared"

// FAQID is the identity value object of the FAQEntry aggregate.
type FAQID struct{ value int64 }

// FAQIDFromInt adapts a database id into the VO.
func FAQIDFromInt(id int64) FAQID { return FAQID{value: id} }

// Int returns the underlying id.
func (f FAQID) Int() int64 { return f.value }

// Localized holds an answer/question pair in a single language.
type Localized struct {
	Question string
	Answer   string
}

// FAQEntry is the aggregate root for a knowledge-base record. It owns its base
// text plus optional localized variants and knows how to pick the best variant
// for a requested language, falling back to the base text.
type FAQEntry struct {
	id       FAQID
	question string
	answer   string
	category string
	locales  map[string]Localized
}

// Reconstitute rebuilds an FAQEntry from persisted state.
func Reconstitute(id FAQID, question, answer, category string, locales map[string]Localized) FAQEntry {
	return FAQEntry{
		id:       id,
		question: question,
		answer:   answer,
		category: category,
		locales:  locales,
	}
}

// ID returns the entry identity.
func (e FAQEntry) ID() FAQID { return e.id }

// Category returns the entry category.
func (e FAQEntry) Category() string { return e.category }

// AnswerFor returns the localized answer for lang, falling back to the base
// answer when no localized variant exists.
func (e FAQEntry) AnswerFor(lang string) string {
	if loc, ok := e.locales[lang]; ok && loc.Answer != "" {
		return loc.Answer
	}
	return e.answer
}

// QuestionFor returns the localized question for lang, falling back to base.
func (e FAQEntry) QuestionFor(lang string) string {
	if loc, ok := e.locales[lang]; ok && loc.Question != "" {
		return loc.Question
	}
	return e.question
}

// SearchResult pairs a matched entry with its similarity score. Similarity is a
// query-time concern, so it lives here rather than on the entry itself.
type SearchResult struct {
	Entry      FAQEntry
	Similarity shared.Confidence
}
