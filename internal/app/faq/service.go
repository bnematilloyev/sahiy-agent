// Package faq is the application service for answering questions from the
// knowledge base. It embeds the query, runs a vector search and either
// synthesizes a retrieval-augmented answer or falls back to a generic LLM reply.
package faq

import (
	"context"
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

// genericConfidence is assigned to answers produced without a strong KB match.
const genericConfidence = 0.5

// Service answers questions from the FAQ knowledge base.
type Service struct {
	repo      knowledge.Repository
	embedder  ai.Embedder
	completer ai.Completer
	threshold float64
	topK      int
	maxTokens int
	mockOnly  bool
	log       *slog.Logger
}

// Config carries the tunables for the FAQ service.
type Config struct {
	Threshold float64
	TopK      int
	MaxTokens int
	MockOnly  bool
}

// New constructs the FAQ service.
func New(repo knowledge.Repository, embedder ai.Embedder, completer ai.Completer, cfg Config, log *slog.Logger) *Service {
	if cfg.TopK <= 0 {
		cfg.TopK = 5
	}
	return &Service{
		repo:      repo,
		embedder:  embedder,
		completer: completer,
		threshold: cfg.Threshold,
		topK:      cfg.TopK,
		maxTokens: cfg.MaxTokens,
		mockOnly:  cfg.MockOnly,
		log:       log,
	}
}

// Answer is the FAQ service result: the reply text and a confidence score.
type Answer struct {
	Text       string
	Confidence shared.Confidence
}

// Respond answers a question, preferring a knowledge-base (RAG) answer and
// falling back to a generic LLM reply.
func (s *Service) Respond(ctx context.Context, history []conversation.Message, query string, lang shared.Language) (Answer, error) {
	results := s.search(ctx, query)

	threshold := s.threshold
	if s.mockOnly {
		threshold = mockThreshold
	}

	if len(results) > 0 && results[0].Similarity.Float() >= threshold {
		text, err := s.ragAnswer(ctx, results, query, lang)
		if err != nil {
			return Answer{}, err
		}
		return Answer{Text: text, Confidence: results[0].Similarity}, nil
	}

	text, err := s.genericAnswer(ctx, history, query, lang)
	if err != nil {
		return Answer{}, err
	}
	return Answer{Text: text, Confidence: shared.NewConfidence(genericConfidence)}, nil
}

// search embeds the query and runs a vector search, falling back to a keyword
// search when embedding fails.
func (s *Service) search(ctx context.Context, query string) []knowledge.SearchResult {
	embedding, err := s.embedder.Embed(ctx, query)
	if err != nil {
		s.log.Warn("faq: embedding failed, using keyword search", "error", err)
		results, kerr := s.repo.SearchByKeyword(ctx, query, s.topK)
		if kerr != nil {
			s.log.Error("faq: keyword search failed", "error", kerr)
		}
		return results
	}

	results, err := s.repo.SearchByVector(ctx, embedding, s.topK)
	if err != nil {
		s.log.Error("faq: vector search failed", "error", err)
		return nil
	}
	return results
}

func (s *Service) ragAnswer(ctx context.Context, results []knowledge.SearchResult, query string, lang shared.Language) (string, error) {
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
	}
	text, err := s.completer.Complete(ctx, req)
	if err != nil {
		return "", fmt.Errorf("faq: rag completion: %w", err)
	}
	return text, nil
}

func (s *Service) genericAnswer(ctx context.Context, history []conversation.Message, query string, lang shared.Language) (string, error) {
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
	}
	text, err := s.completer.Complete(ctx, req)
	if err != nil {
		return "", fmt.Errorf("faq: generic completion: %w", err)
	}
	return text, nil
}
