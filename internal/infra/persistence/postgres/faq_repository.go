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

// keywordMinScore is the lexical score a row must reach to count as a match.
//
// Calibrated against the seeded knowledge base (189 entries, 5 languages):
//
//	                     genuine questions   unrelated questions
//	similarity()         0.18 - 1.00         up to 0.26
//	word_similarity()    0.40 - 1.00         up to 0.35
//
// Plain similarity() cannot separate the two: Chinese scores only 0.18 because
// trigrams work poorly on text without spaces. word_similarity(), which asks how
// well the query matches *part of* a stored question, keeps every genuine hit at
// 0.40 or above, so 0.38 sits in the gap.
//
// The bar does not have to be perfect. A marginal hit still goes to the model,
// which reports its own confidence and escalates when the retrieved context did
// not actually answer the question.
const keywordMinScore = 0.38

// SearchByKeyword is the lexical fallback used when vector search cannot help
// (no embeddings stored, or no embedding provider available).
//
// It scores the query against every localized question with trigram similarity
// and keeps the best language per row, so a Russian question matches the Russian
// column without any transliteration step. The score is returned as the result's
// similarity, which lets callers rank lexical and vector hits the same way.
func (r *FAQRepository) SearchByKeyword(ctx context.Context, query string, topK int) ([]knowledge.SearchResult, error) {
	trimmed := strings.TrimSpace(query)
	if trimmed == "" {
		return nil, nil
	}

	// Each language is scored against its own column, so a Russian question
	// matches question_ru with no transliteration step. Both metrics are taken:
	// similarity() rewards whole-question overlap, word_similarity() rewards a
	// short query matching part of a longer stored question.
	const scoreExpr = `
		GREATEST(
			similarity(question, $1),               word_similarity($1, question),
			similarity(COALESCE(question_uz, ''), $1),  word_similarity($1, COALESCE(question_uz, '')),
			similarity(COALESCE(question_cyr, ''), $1), word_similarity($1, COALESCE(question_cyr, '')),
			similarity(COALESCE(question_ru, ''), $1),  word_similarity($1, COALESCE(question_ru, '')),
			similarity(COALESCE(question_en, ''), $1),  word_similarity($1, COALESCE(question_en, '')),
			similarity(COALESCE(question_zh, ''), $1),  word_similarity($1, COALESCE(question_zh, ''))
		)`

	// The score expression is repeated in WHERE because faqSelectColumns projects
	// COALESCE(...) expressions rather than bare columns: wrapping this in a
	// subquery would leave the outer level with no question_uz to score against.
	q := `
		SELECT ` + faqSelectColumns + `, ` + scoreExpr + ` AS score
		FROM faq_embeddings
		WHERE ` + scoreExpr + ` >= $2
		ORDER BY score DESC
		LIMIT $3`

	rows, err := r.pool.Query(ctx, q, trimmed, keywordMinScore, topK)
	if err != nil {
		return nil, fmt.Errorf("faq: keyword search: %w", err)
	}
	defer rows.Close()
	return scanFAQResults(rows, true)
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

// Add stores a new knowledge-base entry and returns its id.
//
// embedding is left NULL on purpose. Vector search skips NULL rows, but the
// lexical (trigram) path does not, so an entry added here is findable on the
// very next question instead of waiting for an embedding backfill.
func (r *FAQRepository) Add(ctx context.Context, draft knowledge.Draft) (knowledge.FAQID, error) {
	loc := func(code string) (string, string) {
		l := draft.Locales[code]
		return l.Question, l.Answer
	}
	qUz, aUz := loc("uz")
	qCyr, aCyr := loc("cyr")
	qRu, aRu := loc("ru")
	qEn, aEn := loc("en")
	qZh, aZh := loc("zh")

	const q = `
		INSERT INTO faq_embeddings (
			question, answer, category,
			question_uz, answer_uz, question_cyr, answer_cyr,
			question_ru, answer_ru, question_en, answer_en,
			question_zh, answer_zh
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
		RETURNING id`

	var id int64
	err := r.pool.QueryRow(ctx, q,
		draft.Question, draft.Answer, draft.Category,
		qUz, aUz, qCyr, aCyr, qRu, aRu, qEn, aEn, qZh, aZh,
	).Scan(&id)
	if err != nil {
		return knowledge.FAQID{}, fmt.Errorf("faq: add entry: %w", err)
	}
	return knowledge.FAQIDFromInt(id), nil
}
