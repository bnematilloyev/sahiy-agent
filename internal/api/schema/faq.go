package schema

// FAQLocale is one language variant of a knowledge-base entry.
type FAQLocale struct {
	Question string `json:"question"`
	Answer   string `json:"answer"`
}

// IngestFAQRequest adds an entry to the knowledge base.
//
// Question and answer are the base text and are required. Locales is optional
// and keyed by language code (uz, cyr, ru, en, zh); a language left out falls
// back to the base text at read time.
type IngestFAQRequest struct {
	Question string               `json:"question"`
	Answer   string               `json:"answer"`
	Category string               `json:"category"`
	Locales  map[string]FAQLocale `json:"locales"`
}

// IngestFAQResponse returns the id assigned to the new entry.
type IngestFAQResponse struct {
	ID int64 `json:"id"`
}
