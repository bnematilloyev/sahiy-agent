// Package faq is the application service for answering questions from the
// knowledge base. It embeds the query, runs a vector search and either
// synthesizes a retrieval-augmented answer or falls back to a generic LLM reply.
package faq

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/conversation"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/knowledge"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// mockThreshold is the relaxed similarity cutoff used when only mock embeddings
// are available (their cosine similarity is far less meaningful).
const mockThreshold = 0.55

// genericPenalty scales down the model's self-reported confidence when it
// answered without any knowledge-base support. The model is judging its own
// wording; without a KB match there is nothing to check that wording against.
const genericPenalty = 0.8

// Service answers questions from the FAQ knowledge base.
type Service struct {
	repo      knowledge.Repository
	writer    knowledge.Writer
	embedder  ai.Embedder
	completer ai.Completer
	threshold float64
	topK      int
	maxTokens int
	mockOnly  bool
	static    StaticAnswerer
	log       *slog.Logger
}

// StaticAnswerer supplies a fixed answer for questions the knowledge base is
// known not to cover. It is consulted only after retrieval finds nothing, so a
// real knowledge-base entry always wins over hardcoded copy.
type StaticAnswerer interface {
	StaticAnswer(text string, lang shared.Language) (string, bool)
}

// Config carries the tunables for the FAQ service.
type Config struct {
	Threshold float64
	TopK      int
	MaxTokens int
	MockOnly  bool
	// Static is optional; nil disables static fallback answers.
	Static StaticAnswerer
}

// New constructs the FAQ service.
// writer may be nil, which makes the knowledge base read-only.
func New(repo knowledge.Repository, writer knowledge.Writer, embedder ai.Embedder, completer ai.Completer, cfg Config, log *slog.Logger) *Service {
	if cfg.TopK <= 0 {
		cfg.TopK = 5
	}
	return &Service{
		repo:      repo,
		writer:    writer,
		embedder:  embedder,
		completer: completer,
		threshold: cfg.Threshold,
		topK:      cfg.TopK,
		maxTokens: cfg.MaxTokens,
		mockOnly:  cfg.MockOnly,
		static:    cfg.Static,
		log:       log,
	}
}

// Answer is the FAQ service result.
//
// Confidence is the model's own assessment of whether it answered the question,
// NOT the retrieval similarity. Similarity only decides which prompt to use
// (knowledge-base grounded vs generic); a perfect vector match to an entry that
// does not actually cover the question must still yield a low confidence.
//
// Degraded reports that no real model answered, so Text is not usable.
type Answer struct {
	Text       string
	Confidence shared.Confidence
	Degraded   bool
}

// Respond answers a question, preferring a knowledge-base (RAG) answer and
// falling back to a generic LLM reply.
func (s *Service) Respond(ctx context.Context, history []conversation.Message, query string, lang shared.Language) (Answer, error) {
	results, grounded := s.retrieve(ctx, query)

	if grounded {
		out, err := s.ragAnswer(ctx, results, query, lang)
		if err != nil {
			return Answer{}, err
		}
		if out.Degraded {
			// No model is available to phrase an answer, but a knowledge-base
			// entry matched strongly. Serve its stored, human-written text
			// verbatim instead of escalating (parity with the Python service).
			if stored, ok := s.storedAnswer(results[0], lang); ok {
				return stored, nil
			}
		}
		return s.toAnswer(out, 1, "rag"), nil
	}

	// Retrieval found nothing usable. Before spending an LLM call on a guess,
	// check whether this is a question we hold a fixed answer for.
	if s.static != nil {
		if text, ok := s.static.StaticAnswer(query, lang); ok {
			s.log.Debug("faq: serving static answer, no knowledge-base match")
			return Answer{Text: text, Confidence: shared.NewConfidence(1)}, nil
		}
	}

	out, err := s.genericAnswer(ctx, history, query, lang)
	if err != nil {
		return Answer{}, err
	}
	return s.toAnswer(out, genericPenalty, "generic"), nil
}

// storedAnswer returns a knowledge-base entry's own text as the reply. It is
// used only in degraded mode: the copy is human-written and the vector match
// already cleared the similarity threshold, so similarity is the honest
// confidence here - no model was involved to assess anything further.
func (s *Service) storedAnswer(result knowledge.SearchResult, lang shared.Language) (Answer, bool) {
	text := strings.TrimSpace(result.Entry.AnswerFor(lang.Code()))
	if text == "" {
		return Answer{}, false
	}
	s.log.Warn("faq: degraded mode, serving stored knowledge-base answer",
		"faq_id", result.Entry.ID(), "similarity", result.Similarity.Float())
	return Answer{Text: text, Confidence: result.Similarity}, true
}

// toAnswer decodes the answer contract and applies the grounding penalty.
func (s *Service) toAnswer(out ai.Completion, penalty float64, mode string) Answer {
	if out.Degraded {
		return Answer{Degraded: true, Confidence: shared.NewConfidence(0)}
	}
	parsed, contractOK := ai.ParseAnswer(out.Text)
	if !contractOK {
		s.log.Warn("faq: model ignored the answer contract, treating reply as unverified",
			"mode", mode)
	}
	return Answer{
		Text:       parsed.Text,
		Confidence: shared.NewConfidence(parsed.Confidence * penalty),
	}
}

// retrieve finds knowledge-base entries for the query and reports whether they
// are good enough to answer from ("grounded").
//
// Vector search is preferred, but it is only meaningful when a real embedding
// provider answered AND the corpus actually has embeddings stored. Whenever it
// cannot deliver - degraded embedder, search error, or simply no hit - the
// lexical search takes over, so the knowledge base keeps working without an
// embeddings API instead of silently behaving as if it were empty.
func (s *Service) retrieve(ctx context.Context, query string) ([]knowledge.SearchResult, bool) {
	embedding, err := s.embedder.Embed(ctx, query)
	switch {
	case err != nil:
		s.log.Warn("faq: embedding failed, using lexical search", "error", err)
	case embedding.Degraded:
		s.log.Warn("faq: no real embedding provider, using lexical search")
	default:
		results, err := s.repo.SearchByVector(ctx, embedding.Vector, s.topK)
		if err != nil {
			s.log.Error("faq: vector search failed, using lexical search", "error", err)
			break
		}
		if len(results) > 0 && results[0].Similarity.Float() >= s.vectorThreshold() {
			return results, true
		}
		// Either nothing is indexed yet or nothing was similar enough. Lexical
		// search can still find an exact-ish wording match.
		s.log.Debug("faq: no vector match above threshold, trying lexical search",
			"candidates", len(results), "threshold", s.vectorThreshold())
	}

	results, err := s.repo.SearchByKeyword(ctx, query, s.topK)
	if err != nil {
		s.log.Error("faq: lexical search failed", "error", err)
		return nil, false
	}
	if len(results) == 0 {
		return nil, false
	}
	// SearchByKeyword only returns rows that already cleared its own relevance
	// bar, so a hit here is usable context.
	s.log.Debug("faq: lexical match", "hits", len(results),
		"top_score", results[0].Similarity.Float())
	return results, true
}

// vectorThreshold is the similarity a vector hit must reach to count as
// grounded. Mock vectors carry no meaning, so the bar is relaxed when the whole
// chain is mock-only (tests and local runs without any embedding provider).
func (s *Service) vectorThreshold() float64 {
	if s.mockOnly {
		return mockThreshold
	}
	return s.threshold
}

func (s *Service) ragAnswer(ctx context.Context, results []knowledge.SearchResult, query string, lang shared.Language) (ai.Completion, error) {
	var docs strings.Builder
	for i, r := range results {
		docs.WriteString(fmt.Sprintf("%d) Q: %s\n   A: %s\n", i+1,
			r.Entry.QuestionFor(lang.Code()), r.Entry.AnswerFor(lang.Code())))
	}

	req := ai.CompletionRequest{
		System:      ai.RAGSystemPrompt(lang),
		Messages:    []ai.Message{{Role: ai.RoleUser, Content: ai.BuildRAGUser(docs.String(), query)}},
		MaxTokens:   s.maxTokens,
		Temperature: 0.2,
		Route:       "rag",
	}
	out, err := s.completer.Complete(ctx, req)
	if err != nil {
		return ai.Completion{}, fmt.Errorf("faq: rag completion: %w", err)
	}
	return out, nil
}

func (s *Service) genericAnswer(ctx context.Context, history []conversation.Message, query string, lang shared.Language) (ai.Completion, error) {
	messages := make([]ai.Message, 0, len(history)+1)
	for _, m := range history {
		messages = append(messages, ai.Message{Role: string(m.Role()), Content: m.Content().String()})
	}
	messages = append(messages, ai.Message{Role: ai.RoleUser, Content: query})

	req := ai.CompletionRequest{
		System:      ai.GenericSystemPrompt(lang),
		Messages:    messages,
		MaxTokens:   s.maxTokens,
		Temperature: 0.3,
		Route:       "generic",
	}
	out, err := s.completer.Complete(ctx, req)
	if err != nil {
		return ai.Completion{}, fmt.Errorf("faq: generic completion: %w", err)
	}
	return out, nil
}

// ErrEmptyEntry rejects a knowledge-base entry with nothing to match or answer.
var ErrEmptyEntry = errors.New("faq: question and answer are required")

// defaultCategory keeps the category column non-empty, matching the seeded rows.
const defaultCategory = "general"

// Ingest adds an entry to the knowledge base.
//
// It is how the assistant is taught: an operator who had to answer a question
// by hand can add it, and the next customer to ask gets it from the FAQ. The
// entry is usable immediately because retrieval falls back to lexical search.
func (s *Service) Ingest(ctx context.Context, draft knowledge.Draft) (knowledge.FAQID, error) {
	if s.writer == nil {
		return knowledge.FAQID{}, errors.New("faq: knowledge base is read-only")
	}
	draft.Question = strings.TrimSpace(draft.Question)
	draft.Answer = strings.TrimSpace(draft.Answer)
	if draft.Question == "" || draft.Answer == "" {
		return knowledge.FAQID{}, ErrEmptyEntry
	}
	if draft.Category = strings.TrimSpace(draft.Category); draft.Category == "" {
		draft.Category = defaultCategory
	}

	id, err := s.writer.Add(ctx, draft)
	if err != nil {
		return knowledge.FAQID{}, err
	}
	s.log.Info("faq: knowledge base entry added", "faq_id", id.Int(), "category", draft.Category)
	return id, nil
}
