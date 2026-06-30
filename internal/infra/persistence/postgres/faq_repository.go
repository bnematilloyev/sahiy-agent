package postgres

import (
	"context"
	"fmt"
	"strconv"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/knowledge"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// FAQRepository is the pgx-backed implementation of knowledge.Repository.
// SearchByVector uses pgvector cosine distance (similarity = 1 - distance);
// SearchByKeyword is a simple ILIKE fallback.
type FAQRepository struct {
	pool *pgxpool.Pool
}

// NewFAQRepository constructs the repository.
func NewFAQRepository(pool *pgxpool.Pool) *FAQRepository {
	return &FAQRepository{pool: pool}
}

const faqSelectColumns = `
	id, question, answer, category,
	COALESCE(question_uz, ''),  COALESCE(answer_uz, ''),
	COALESCE(question_cyr, ''), COALESCE(answer_cyr, ''),
	COALESCE(question_ru, ''),  COALESCE(answer_ru, ''),
	COALESCE(question_en, ''),  COALESCE(answer_en, ''),
	COALESCE(question_zh, ''),  COALESCE(answer_zh, '')`

func (r *FAQRepository) SearchByVector(ctx context.Context, embedding []float32, topK int) ([]knowledge.SearchResult, error) {
	if len(embedding) == 0 {
		return nil, nil
	}
	vec := encodeVector(embedding)
	q := `
		SELECT ` + faqSelectColumns + `, 1 - (embedding <=> $1) AS similarity
		FROM faq_embeddings
		WHERE embedding IS NOT NULL
		ORDER BY embedding <=> $1
		LIMIT $2`

	rows, err := r.pool.Query(ctx, q, vec, topK)
	if err != nil {
		return nil, fmt.Errorf("faq: vector search: %w", err)
	}
	defer rows.Close()
	return scanFAQResults(rows, true)
}

func (r *FAQRepository) SearchByKeyword(ctx context.Context, query string, topK int) ([]knowledge.SearchResult, error) {
	pattern := "%" + strings.TrimSpace(query) + "%"
	q := `
		SELECT ` + faqSelectColumns + `
		FROM faq_embeddings
		WHERE question ILIKE $1 OR answer ILIKE $1
		LIMIT $2`

	rows, err := r.pool.Query(ctx, q, pattern, topK)
	if err != nil {
		return nil, fmt.Errorf("faq: keyword search: %w", err)
	}
	defer rows.Close()
	return scanFAQResults(rows, false)
}

func scanFAQResults(rows pgx.Rows, withSimilarity bool) ([]knowledge.SearchResult, error) {
	var out []knowledge.SearchResult
	for rows.Next() {
		var (
			id                           int64
			question, answer, category   string
			qUz, aUz, qCyr, aCyr         string
			qRu, aRu, qEn, aEn, qZh, aZh string
			similarity                   float64
		)
		dest := []any{
			&id, &question, &answer, &category,
			&qUz, &aUz, &qCyr, &aCyr,
			&qRu, &aRu, &qEn, &aEn, &qZh, &aZh,
		}
		if withSimilarity {
			dest = append(dest, &similarity)
		}
		if err := rows.Scan(dest...); err != nil {
			return nil, fmt.Errorf("faq: scan: %w", err)
		}

		locales := map[string]knowledge.Localized{
			"uz":  {Question: qUz, Answer: aUz},
			"cyr": {Question: qCyr, Answer: aCyr},
			"ru":  {Question: qRu, Answer: aRu},
			"en":  {Question: qEn, Answer: aEn},
			"zh":  {Question: qZh, Answer: aZh},
		}
		entry := knowledge.Reconstitute(knowledge.FAQIDFromInt(id), question, answer, category, locales)
		out = append(out, knowledge.SearchResult{
			Entry:      entry,
			Similarity: shared.NewConfidence(similarity),
		})
	}
	return out, rows.Err()
}

// encodeVector renders a float slice as a pgvector text literal: [1,2,3].
func encodeVector(v []float32) string {
	var b strings.Builder
	b.WriteByte('[')
	for i, f := range v {
		if i > 0 {
			b.WriteByte(',')
		}
		b.WriteString(strconv.FormatFloat(float64(f), 'f', -1, 32))
	}
	b.WriteByte(']')
	return b.String()
}
