package llm

import (
	"context"
	"errors"
	"net/http"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
)

const anthropicURL = "https://api.anthropic.com/v1/messages"
const anthropicVersion = "2023-06-01"

// AnthropicClient is a Completer backed by the Anthropic Messages API.
type AnthropicClient struct {
	apiKey string
	model  string
	http   *http.Client
}

// NewAnthropicClient constructs an Anthropic-backed completer.
func NewAnthropicClient(apiKey, model string, timeout time.Duration) *AnthropicClient {
	return &AnthropicClient{
		apiKey: apiKey,
		model:  model,
		http:   &http.Client{Timeout: timeout},
	}
}

// Available reports whether an API key is configured.
func (c *AnthropicClient) Available() bool { return c.apiKey != "" }

type anthropicRequest struct {
	Model       string             `json:"model"`
	MaxTokens   int                `json:"max_tokens"`
	System      string             `json:"system,omitempty"`
	Temperature float64            `json:"temperature"`
	Messages    []anthropicMessage `json:"messages"`
}

type anthropicMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type anthropicResponse struct {
	Content []struct {
		Type string `json:"type"`
		Text string `json:"text"`
	} `json:"content"`
}

// Complete implements ai.Completer.
func (c *AnthropicClient) Complete(ctx context.Context, req ai.CompletionRequest) (string, error) {
	if !c.Available() {
		return "", errors.New("anthropic: missing api key")
	}

	maxTokens := req.MaxTokens
	if maxTokens <= 0 {
		maxTokens = 1024
	}

	body := anthropicRequest{
		Model:       c.model,
		MaxTokens:   maxTokens,
		System:      req.System,
		Temperature: req.Temperature,
		Messages:    toAnthropicMessages(req.Messages),
	}
	headers := map[string]string{
		"x-api-key":         c.apiKey,
		"anthropic-version": anthropicVersion,
	}

	var out anthropicResponse
	if err := postJSON(ctx, c.http, anthropicURL, headers, body, &out); err != nil {
		return "", err
	}
	for _, block := range out.Content {
		if block.Type == "text" && block.Text != "" {
			return block.Text, nil
		}
	}
	return "", errors.New("anthropic: empty completion")
}

// toAnthropicMessages keeps only user/assistant turns (system is sent separately).
func toAnthropicMessages(msgs []ai.Message) []anthropicMessage {
	out := make([]anthropicMessage, 0, len(msgs))
	for _, m := range msgs {
		if m.Role == ai.RoleSystem {
			continue
		}
		out = append(out, anthropicMessage{Role: m.Role, Content: m.Content})
	}
	return out
}
