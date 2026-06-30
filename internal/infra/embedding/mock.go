package embedding

import (
	"context"
	"hash/fnv"
	"math"
)

// MockEmbedder produces deterministic pseudo-random unit vectors from text. It
// lets the system run (and tests pass) without any embedding API. Similarity is
// far less meaningful than real embeddings, so callers should use a lower RAG
// threshold when relying on it.
type MockEmbedder struct {
	dim int
}

// NewMockEmbedder constructs a mock embedder of the given dimension.
func NewMockEmbedder(dim int) *MockEmbedder {
	if dim <= 0 {
		dim = 1536
	}
	return &MockEmbedder{dim: dim}
}

// Embed implements ai.Embedder with a deterministic hash-seeded vector.
func (e *MockEmbedder) Embed(_ context.Context, text string) ([]float32, error) {
	seed := fnv.New64a()
	_, _ = seed.Write([]byte(text))
	state := seed.Sum64()

	vec := make([]float32, e.dim)
	var norm float64
	for i := 0; i < e.dim; i++ {
		// xorshift64 for cheap deterministic pseudo-randomness.
		state ^= state << 13
		state ^= state >> 7
		state ^= state << 17
		v := float64(int64(state%2000)-1000) / 1000.0
		vec[i] = float32(v)
		norm += v * v
	}

	norm = math.Sqrt(norm)
	if norm > 0 {
		for i := range vec {
			vec[i] = float32(float64(vec[i]) / norm)
		}
	}
	return vec, nil
}
