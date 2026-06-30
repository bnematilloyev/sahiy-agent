// Package embedding provides Embedder adapters (OpenAI, a deterministic mock)
// and a fallback that degrades gracefully when the API is unavailable.
package embedding

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"time"
)

const openAIEmbeddingURL = "https://api.openai.com/v1/embeddings"

// OpenAIEmbedder calls the OpenAI embeddings API.
type OpenAIEmbedder struct {
	apiKey string
	model  string
	http   *http.Client
}

// NewOpenAIEmbedder constructs an OpenAI-backed embedder.
func NewOpenAIEmbedder(apiKey, model string, timeout time.Duration) *OpenAIEmbedder {
	return &OpenAIEmbedder{
		apiKey: apiKey,
		model:  model,
		http:   &http.Client{Timeout: timeout},
	}
}

type embeddingRequest struct {
	Model string `json:"model"`
	Input string `json:"input"`
}

type embeddingResponse struct {
	Data []struct {
		Embedding []float32 `json:"embedding"`
	} `json:"data"`
}

// Embed implements ai.Embedder.
func (e *OpenAIEmbedder) Embed(ctx context.Context, text string) ([]float32, error) {
	if e.apiKey == "" {
		return nil, errors.New("openai embedder: missing api key")
	}

	payload, err := json.Marshal(embeddingRequest{Model: e.model, Input: text})
	if err != nil {
		return nil, fmt.Errorf("openai embedder: marshal: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, openAIEmbeddingURL, bytes.NewReader(payload))
	if err != nil {
		return nil, fmt.Errorf("openai embedder: build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+e.apiKey)

	resp, err := e.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("openai embedder: do request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		snippet, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return nil, fmt.Errorf("openai embedder: http %d: %s", resp.StatusCode, snippet)
	}

	var out embeddingResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, fmt.Errorf("openai embedder: decode: %w", err)
	}
	if len(out.Data) == 0 || len(out.Data[0].Embedding) == 0 {
		return nil, errors.New("openai embedder: empty embedding")
	}
	return out.Data[0].Embedding, nil
}
