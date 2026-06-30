package llm

import (
	"context"
	"errors"
	"net/http"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
)

const openAIChatURL = "https://api.openai.com/v1/chat/completions"

// OpenAIClient is a Completer backed by the OpenAI Chat Completions API.
type OpenAIClient struct {
	apiKey string
	model  string
	http   *http.Client
}

// NewOpenAIClient constructs an OpenAI-backed completer.
func NewOpenAIClient(apiKey, model string, timeout time.Duration) *OpenAIClient {
	return &OpenAIClient{
		apiKey: apiKey,
		model:  model,
		http:   &http.Client{Timeout: timeout},
	}
}

// Available reports whether an API key is configured.
func (c *OpenAIClient) Available() bool { return c.apiKey != "" }

type openAIRequest struct {
	Model       string          `json:"model"`
	Messages    []openAIMessage `json:"messages"`
	MaxTokens   int             `json:"max_tokens,omitempty"`
	Temperature float64         `json:"temperature"`
}

type openAIMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type openAIResponse struct {
	Choices []struct {
		Message openAIMessage `json:"message"`
	} `json:"choices"`
}

// Complete implements ai.Completer.
func (c *OpenAIClient) Complete(ctx context.Context, req ai.CompletionRequest) (string, error) {
	if !c.Available() {
		return "", errors.New("openai: missing api key")
	}

	messages := make([]openAIMessage, 0, len(req.Messages)+1)
	if req.System != "" {
		messages = append(messages, openAIMessage{Role: ai.RoleSystem, Content: req.System})
	}
	for _, m := range req.Messages {
		messages = append(messages, openAIMessage{Role: m.Role, Content: m.Content})
	}

	body := openAIRequest{
		Model:       c.model,
		Messages:    messages,
		MaxTokens:   req.MaxTokens,
		Temperature: req.Temperature,
	}
	headers := map[string]string{"Authorization": "Bearer " + c.apiKey}

	var out openAIResponse
	if err := postJSON(ctx, c.http, openAIChatURL, headers, body, &out); err != nil {
		return "", err
	}
	if len(out.Choices) == 0 || out.Choices[0].Message.Content == "" {
		return "", errors.New("openai: empty completion")
	}
	return out.Choices[0].Message.Content, nil
}
