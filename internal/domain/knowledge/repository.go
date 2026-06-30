package knowledge

import "context"

// Repository is the persistence port for the FAQ knowledge base.
type Repository interface {
	// SearchByVector returns the top-k entries ranked by cosine similarity.
	SearchByVector(ctx context.Context, embedding []float32, topK int) ([]SearchResult, error)
	// SearchByKeyword is the fallback used when embeddings are unavailable.
	SearchByKeyword(ctx context.Context, query string, topK int) ([]SearchResult, error)
}
