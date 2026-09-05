package postgres

import (
	"context"
	_ "embed"
	"encoding/json"
	"fmt"
	"log/slog"

	"github.com/jackc/pgx/v5/pgxpool"
)

// faqSeedJSON is the baseline knowledge base, compiled into the binary so a
// fresh deployment comes up answering questions without any external tooling.
//
//go:embed seeds/faq.json
var faqSeedJSON []byte

// faqSeedEntry mirrors one row of faq_embeddings. Localized fields are optional;
// an empty one falls back to the base question/answer at read time.
type faqSeedEntry struct {
	ID       int64  `json:"id"`
	Category string `json:"category"`
	Question string `json:"question"`
	Answer   string `json:"answer"`

	QuestionUz  string `json:"question_uz"`
	AnswerUz    string `json:"answer_uz"`
	QuestionCyr string `json:"question_cyr"`
	AnswerCyr   string `json:"answer_cyr"`
	QuestionRu  string `json:"question_ru"`
	AnswerRu    string `json:"answer_ru"`
	QuestionEn  string `json:"question_en"`
	AnswerEn    string `json:"answer_en"`
	QuestionZh  string `json:"question_zh"`
	AnswerZh    string `json:"answer_zh"`
}

// SeedFAQ inserts the baseline knowledge base on startup.
//
// It is INSERT-only (ON CONFLICT DO NOTHING): entries the operators have since
// edited in the database are never overwritten, and embeddings computed later
// are never wiped. Adding an entry to seeds/faq.json makes it appear on the next
// start; changing existing copy there does NOT rewrite a row that already
// exists, which is deliberate - the database is the source of truth once the
// service is live.
func SeedFAQ(ctx context.Context, pool *pgxpool.Pool, log *slog.Logger) error {
	var entries []faqSeedEntry
	if err := json.Unmarshal(faqSeedJSON, &entries); err != nil {
		return fmt.Errorf("postgres: parse faq seed: %w", err)
	}
	if len(entries) == 0 {
		return nil
	}

	cols := newFAQSeedColumns(len(entries))
	for _, e := range entries {
		if e.ID <= 0 || e.Question == "" || e.Answer == "" {
			log.Warn("postgres: skipping malformed faq seed entry", "id", e.ID)
			continue
		}
		cols.add(e)
	}

	const q = `
		INSERT INTO faq_embeddings (
			id, question, answer, category,
			question_uz, answer_uz, question_cyr, answer_cyr,
			question_ru, answer_ru, question_en, answer_en,
			question_zh, answer_zh
		)
		SELECT * FROM unnest(
			$1::bigint[], $2::text[], $3::text[], $4::text[],
			$5::text[], $6::text[], $7::text[], $8::text[],
			$9::text[], $10::text[], $11::text[], $12::text[],
			$13::text[], $14::text[]
		)
		ON CONFLICT (id) DO NOTHING`

	tag, err := pool.Exec(ctx, q, cols.args()...)
	if err != nil {
		return fmt.Errorf("postgres: seed faq: %w", err)
	}

	// Keep the sequence past the seeded ids, or the first operator-created entry
	// would collide with a seeded primary key.
	const resync = `
		SELECT setval(
			pg_get_serial_sequence('faq_embeddings', 'id'),
			GREATEST((SELECT COALESCE(MAX(id), 1) FROM faq_embeddings), 1)
		)`
	if _, err := pool.Exec(ctx, resync); err != nil {
		return fmt.Errorf("postgres: resync faq id sequence: %w", err)
	}

	if inserted := tag.RowsAffected(); inserted > 0 {
		log.Info("faq seed applied", "inserted", inserted, "available", len(entries))
	} else {
		log.Debug("faq seed up to date", "available", len(entries))
	}
	return nil
}

// faqSeedColumns accumulates entries column-wise, which is the shape the
// unnest-based bulk insert needs.
type faqSeedColumns struct {
	ids                        []int64
	question, answer, category []string
	questionUz, answerUz       []string
	questionCyr, answerCyr     []string
	questionRu, answerRu       []string
	questionEn, answerEn       []string
	questionZh, answerZh       []string
}

func newFAQSeedColumns(n int) *faqSeedColumns {
	c := &faqSeedColumns{}
	c.ids = make([]int64, 0, n)
	for _, s := range c.textColumns() {
		*s = make([]string, 0, n)
	}
	return c
}

// textColumns lists the text columns in the same order as the INSERT statement.
func (c *faqSeedColumns) textColumns() []*[]string {
	return []*[]string{
		&c.question, &c.answer, &c.category,
		&c.questionUz, &c.answerUz, &c.questionCyr, &c.answerCyr,
		&c.questionRu, &c.answerRu, &c.questionEn, &c.answerEn,
		&c.questionZh, &c.answerZh,
	}
}

func (c *faqSeedColumns) add(e faqSeedEntry) {
	c.ids = append(c.ids, e.ID)
	values := []string{
		e.Question, e.Answer, e.Category,
		e.QuestionUz, e.AnswerUz, e.QuestionCyr, e.AnswerCyr,
		e.QuestionRu, e.AnswerRu, e.QuestionEn, e.AnswerEn,
		e.QuestionZh, e.AnswerZh,
	}
	for i, col := range c.textColumns() {
		*col = append(*col, values[i])
	}
}

func (c *faqSeedColumns) args() []any {
	args := []any{c.ids}
	for _, col := range c.textColumns() {
		args = append(args, *col)
	}
	return args
}
