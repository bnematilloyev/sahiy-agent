package faq

import (
	"context"
	"io"
	"log/slog"
	"testing"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/knowledge"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

type fixedCompleter struct{ out ai.Completion }

func (c fixedCompleter) Available() bool { return !c.out.Degraded }

func (c fixedCompleter) Complete(context.Context, ai.CompletionRequest) (ai.Completion, error) {
	return c.out, nil
}

type matchRepo struct{ results []knowledge.SearchResult }

func (r matchRepo) SearchByVector(context.Context, []float32, int) ([]knowledge.SearchResult, error) {
	return r.results, nil
}

func (r matchRepo) SearchByKeyword(context.Context, string, int) ([]knowledge.SearchResult, error) {
	return r.results, nil
}

type okEmbedder struct{}

func (okEmbedder) Embed(context.Context, string) (ai.Embedding, error) {
	return ai.Embedding{Vector: []float32{0.1}}, nil
}

// degradedEmbedder stands in for "OpenAI is down, only the mock answered".
type degradedEmbedder struct{}

func (degradedEmbedder) Embed(context.Context, string) (ai.Embedding, error) {
	return ai.Embedding{Vector: []float32{0.1}, Degraded: true}, nil
}

func strongMatch() []knowledge.SearchResult {
	entry := knowledge.Reconstitute(
		knowledge.FAQIDFromInt(7),
		"Yetkazib berish qancha vaqt oladi?",
		"Yetkazib berish odatda 7-10 kun.",
		"delivery",
		map[string]knowledge.Localized{
			"ru": {Question: "Сколько идёт доставка?", Answer: "Доставка обычно занимает 7-10 дней."},
		},
	)
	return []knowledge.SearchResult{{Entry: entry, Similarity: shared.NewConfidence(0.93)}}
}

func newService(t *testing.T, out ai.Completion, results []knowledge.SearchResult) *Service {
	t.Helper()
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	return New(matchRepo{results: results}, nil, okEmbedder{}, fixedCompleter{out: out},
		Config{Threshold: 0.85, TopK: 3}, log)
}

// With no model available but a strong knowledge-base hit, the stored answer is
// served verbatim rather than escalating - this is what the Python service did.
func TestRespondServesStoredAnswerWhenDegraded(t *testing.T) {
	svc := newService(t, ai.Completion{Degraded: true}, strongMatch())

	ans, err := svc.Respond(context.Background(), nil, "yetkazib berish qancha vaqt?", shared.LangUz)
	if err != nil {
		t.Fatalf("Respond: %v", err)
	}
	if ans.Degraded {
		t.Error("Degraded = true, want a usable stored answer")
	}
	if ans.Text != "Yetkazib berish odatda 7-10 kun." {
		t.Errorf("Text = %q, want the stored answer", ans.Text)
	}
}

func TestRespondServesStoredAnswerInRequestedLanguage(t *testing.T) {
	svc := newService(t, ai.Completion{Degraded: true}, strongMatch())

	ans, err := svc.Respond(context.Background(), nil, "сколько идёт доставка?", shared.LangRu)
	if err != nil {
		t.Fatalf("Respond: %v", err)
	}
	if ans.Text != "Доставка обычно занимает 7-10 дней." {
		t.Errorf("Text = %q, want the Russian variant", ans.Text)
	}
}

// Degraded with nothing in the knowledge base: there is no honest answer to
// give, so the caller must be told to escalate.
func TestRespondReportsDegradedWithoutKnowledgeBaseMatch(t *testing.T) {
	svc := newService(t, ai.Completion{Degraded: true}, nil)

	ans, err := svc.Respond(context.Background(), nil, "kafolat qancha muddat?", shared.LangUz)
	if err != nil {
		t.Fatalf("Respond: %v", err)
	}
	if !ans.Degraded {
		t.Error("Degraded = false, want true so the caller escalates")
	}
}

// A weak vector hit must not be dressed up as a confident answer just because
// retrieval returned something.
func TestRespondUsesModelConfidenceNotSimilarity(t *testing.T) {
	svc := newService(t,
		ai.Completion{Text: `{"answer":"Aniq ayta olmayman.","confidence":0.15}`},
		strongMatch())

	ans, err := svc.Respond(context.Background(), nil, "yetkazib berish qancha vaqt?", shared.LangUz)
	if err != nil {
		t.Fatalf("Respond: %v", err)
	}
	if got := ans.Confidence.Float(); got != 0.15 {
		t.Errorf("Confidence = %v, want the model's 0.15 rather than the 0.93 similarity", got)
	}
}

type companyStatic struct{}

func (companyStatic) StaticAnswer(text string, _ shared.Language) (string, bool) {
	if text == "sahiy nima?" {
		return "STATIC COMPANY BLURB", true
	}
	return "", false
}

func newServiceWithStatic(t *testing.T, out ai.Completion, results []knowledge.SearchResult) *Service {
	t.Helper()
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	return New(matchRepo{results: results}, nil, okEmbedder{}, fixedCompleter{out: out},
		Config{Threshold: 0.85, TopK: 3, Static: companyStatic{}}, log)
}

// The static blurb is a last resort: it must never shadow a real knowledge-base
// entry, otherwise editing the FAQ table stops changing what customers see.
func TestKnowledgeBaseAnswerBeatsStaticAnswer(t *testing.T) {
	svc := newServiceWithStatic(t,
		ai.Completion{Text: `{"answer":"Bazadagi javob.","confidence":0.9}`},
		strongMatch())

	ans, err := svc.Respond(context.Background(), nil, "sahiy nima?", shared.LangUz)
	if err != nil {
		t.Fatalf("Respond: %v", err)
	}
	if ans.Text != "Bazadagi javob." {
		t.Errorf("Text = %q, want the knowledge-base answer to win", ans.Text)
	}
}

// With nothing in the knowledge base, the static blurb answers instead of
// spending an LLM call on a guess.
func TestStaticAnswerUsedWhenKnowledgeBaseMisses(t *testing.T) {
	svc := newServiceWithStatic(t,
		ai.Completion{Text: `{"answer":"O'ylab topilgan javob.","confidence":0.9}`},
		nil)

	ans, err := svc.Respond(context.Background(), nil, "sahiy nima?", shared.LangUz)
	if err != nil {
		t.Fatalf("Respond: %v", err)
	}
	if ans.Text != "STATIC COMPANY BLURB" {
		t.Errorf("Text = %q, want the static answer", ans.Text)
	}
}

// keywordRepo answers only the lexical search, so a test can prove the service
// fell back to it rather than using vector results.
type keywordRepo struct{ results []knowledge.SearchResult }

func (keywordRepo) SearchByVector(context.Context, []float32, int) ([]knowledge.SearchResult, error) {
	return nil, nil
}

func (r keywordRepo) SearchByKeyword(context.Context, string, int) ([]knowledge.SearchResult, error) {
	return r.results, nil
}

func newServiceWithRepo(t *testing.T, repo knowledge.Repository, emb ai.Embedder, out ai.Completion) *Service {
	t.Helper()
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	return New(repo, nil, emb, fixedCompleter{out: out}, Config{Threshold: 0.85, TopK: 3}, log)
}

// The bug this fixes: the mock embedder answered successfully, so the service
// ran a meaningless vector search and concluded the knowledge base was empty -
// disabling the very lexical fallback that exists for this situation.
func TestDegradedEmbedderFallsBackToLexicalSearch(t *testing.T) {
	svc := newServiceWithRepo(t,
		keywordRepo{results: strongMatch()},
		degradedEmbedder{},
		ai.Completion{Text: `{"answer":"Bazadan javob.","confidence":0.9}`})

	ans, err := svc.Respond(context.Background(), nil, "yetkazib berish qancha vaqt?", shared.LangUz)
	if err != nil {
		t.Fatalf("Respond: %v", err)
	}
	if ans.Text != "Bazadan javob." {
		t.Errorf("Text = %q, want a knowledge-base grounded answer via lexical search", ans.Text)
	}
}

// A real embedder that finds nothing (corpus not embedded yet) must also reach
// the lexical search instead of going straight to a generic guess.
func TestEmptyVectorResultFallsBackToLexicalSearch(t *testing.T) {
	svc := newServiceWithRepo(t,
		keywordRepo{results: strongMatch()},
		okEmbedder{},
		ai.Completion{Text: `{"answer":"Bazadan javob.","confidence":0.9}`})

	ans, err := svc.Respond(context.Background(), nil, "yetkazib berish qancha vaqt?", shared.LangUz)
	if err != nil {
		t.Fatalf("Respond: %v", err)
	}
	if ans.Text != "Bazadan javob." {
		t.Errorf("Text = %q, want the lexical fallback to ground the answer", ans.Text)
	}
}

// With nothing found by either search the service must not pretend to be
// grounded; it goes to the generic path and takes the confidence penalty.
func TestNoMatchAnywhereUsesGenericPath(t *testing.T) {
	svc := newServiceWithRepo(t,
		keywordRepo{results: nil},
		okEmbedder{},
		ai.Completion{Text: `{"answer":"Aniq bilmayman.","confidence":0.5}`})

	ans, err := svc.Respond(context.Background(), nil, "marsdagi ob-havo?", shared.LangUz)
	if err != nil {
		t.Fatalf("Respond: %v", err)
	}
	if got := ans.Confidence.Float(); got >= 0.5 {
		t.Errorf("Confidence = %v, want the generic grounding penalty applied", got)
	}
}

// Degraded embedder AND degraded model: the stored knowledge-base text is still
// the right answer, reached purely through lexical search and plain SQL.
func TestFullyDegradedStillAnswersFromKnowledgeBase(t *testing.T) {
	svc := newServiceWithRepo(t,
		keywordRepo{results: strongMatch()},
		degradedEmbedder{},
		ai.Completion{Degraded: true})

	ans, err := svc.Respond(context.Background(), nil, "yetkazib berish qancha vaqt?", shared.LangUz)
	if err != nil {
		t.Fatalf("Respond: %v", err)
	}
	if ans.Degraded {
		t.Error("Degraded = true, want the stored answer to be served")
	}
	if ans.Text != "Yetkazib berish odatda 7-10 kun." {
		t.Errorf("Text = %q, want the stored knowledge-base answer", ans.Text)
	}
}
