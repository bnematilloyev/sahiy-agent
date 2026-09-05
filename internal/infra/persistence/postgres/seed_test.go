package postgres

import (
	"encoding/json"
	"testing"
)

func loadSeed(t *testing.T) []faqSeedEntry {
	t.Helper()
	var entries []faqSeedEntry
	if err := json.Unmarshal(faqSeedJSON, &entries); err != nil {
		t.Fatalf("embedded faq seed is not valid JSON: %v", err)
	}
	if len(entries) == 0 {
		t.Fatal("embedded faq seed is empty")
	}
	return entries
}

// The seed ships inside the binary, so a malformed file breaks startup for every
// deployment. Catch it at build time instead.
func TestFAQSeedIsWellFormed(t *testing.T) {
	for _, e := range loadSeed(t) {
		if e.ID <= 0 {
			t.Errorf("entry with non-positive id: %+v", e)
		}
		if e.Question == "" || e.Answer == "" {
			t.Errorf("id=%d has empty base question/answer", e.ID)
		}
		if e.Category == "" {
			t.Errorf("id=%d has empty category", e.ID)
		}
	}
}

// Duplicate ids would be silently swallowed by ON CONFLICT DO NOTHING, so one
// entry would vanish without a trace.
func TestFAQSeedIDsAreUnique(t *testing.T) {
	seen := map[int64]string{}
	for _, e := range loadSeed(t) {
		if prev, dup := seen[e.ID]; dup {
			t.Errorf("duplicate id=%d: %q and %q", e.ID, prev, e.Question)
		}
		seen[e.ID] = e.Question
	}
}

// Every supported reply language needs its own copy, or customers silently get
// answers in the wrong language via the base-text fallback.
func TestFAQSeedCoversEveryLanguage(t *testing.T) {
	entries := loadSeed(t)
	missing := map[string]int{}
	for _, e := range entries {
		for lang, text := range map[string][2]string{
			"uz":  {e.QuestionUz, e.AnswerUz},
			"cyr": {e.QuestionCyr, e.AnswerCyr},
			"ru":  {e.QuestionRu, e.AnswerRu},
			"en":  {e.QuestionEn, e.AnswerEn},
			"zh":  {e.QuestionZh, e.AnswerZh},
		} {
			if text[0] == "" || text[1] == "" {
				missing[lang]++
			}
		}
	}
	for lang, n := range missing {
		t.Errorf("%d of %d entries are missing %s text", n, len(entries), lang)
	}
}

// The column accumulator feeds a positional unnest(); a length mismatch would
// shift every value into the wrong column.
func TestFAQSeedColumnsStayAligned(t *testing.T) {
	entries := loadSeed(t)
	cols := newFAQSeedColumns(len(entries))
	for _, e := range entries {
		cols.add(e)
	}

	args := cols.args()
	if len(args) != 14 {
		t.Fatalf("args = %d, want 14 to match the INSERT column list", len(args))
	}
	if len(cols.ids) != len(entries) {
		t.Errorf("ids = %d, want %d", len(cols.ids), len(entries))
	}
	for i, col := range cols.textColumns() {
		if len(*col) != len(entries) {
			t.Errorf("text column %d has %d values, want %d", i, len(*col), len(entries))
		}
	}
}

// Guards against a truncated regeneration of the seed file.
func TestFAQSeedHasExpectedSize(t *testing.T) {
	if n := len(loadSeed(t)); n < 150 {
		t.Errorf("seed has only %d entries; the knowledge base looks truncated", n)
	}
}
