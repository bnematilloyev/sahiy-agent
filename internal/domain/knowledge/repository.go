package knowledge

import "context"

// Repository is the persistence port for the FAQ knowledge base.
type Repository interface {
	// SearchByVector returns the top-k entries ranked by cosine similarity.
	SearchByVector(ctx context.Context, embedding []float32, topK int) ([]SearchResult, error)
	// SearchByKeyword is the fallback used when embeddings are unavailable.
	SearchByKeyword(ctx context.Context, query string, topK int) ([]SearchResult, error)
}

// Writer is the port for growing the knowledge base at runtime.
//
// It is separate from Repository so that read-side implementations (and the
// fakes in tests) are not forced to implement a write path they never use.
type Writer interface {
	// Add stores a new entry and returns its assigned id. The entry is stored
	// without an embedding: retrieval falls back to lexical search, so a new
	// entry is answerable immediately rather than only after an embedding run.
	Add(ctx context.Context, draft Draft) (FAQID, error)
}

// Draft is a new knowledge-base entry before it has an identity.
type Draft struct {
	Question string
	Answer   string
	Category string
	// Locales holds optional per-language variants keyed by language code.
	Locales map[string]Localized
}
