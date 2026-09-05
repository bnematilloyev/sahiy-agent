package llm

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"sync/atomic"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
)

// anthropicURL is a var (not const) so tests can point it at a local server.
var anthropicURL = "https://api.anthropic.com/v1/messages"

const anthropicVersion = "2023-06-01"

// AnthropicClient is a Completer backed by the Anthropic Messages API.
type AnthropicClient struct {
	apiKey string
	model  string
	http   *http.Client
	// noTemperature is learned lazily: some models (Opus 4.7+, Sonnet 5) reject
	// the temperature field outright with a 400, even when it is the default.
	// Once a model tells us that, every later call on this client skips the
	// field instead of paying for another round trip and 400.
	noTemperature atomic.Bool
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
	System      []anthropicBlock   `json:"system,omitempty"`
	Temperature *float64           `json:"temperature,omitempty"`
	Messages    []anthropicMessage `json:"messages"`
}

type anthropicMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// anthropicBlock is a system-prompt content block. Every system prompt in this
// codebase (see internal/app/ai/prompts.go) is a fixed set of instructions with
// no per-request data mixed in, so it is always marked cacheable: identical
// system text across calls (same route, same language) then hits Anthropic's
// prompt cache instead of being billed and processed as fresh input every time.
type anthropicBlock struct {
	Type         string        `json:"type"`
	Text         string        `json:"text"`
	CacheControl *cacheControl `json:"cache_control,omitempty"`
}

type cacheControl struct {
	Type string `json:"type"`
}

// ephemeralCache marks a content block for Anthropic's (default 5-minute)
// ephemeral prompt cache. Blocks under the model's minimum cacheable length are
// simply processed as normal input - the field is a no-op, not an error.
var ephemeralCache = &cacheControl{Type: "ephemeral"}

type anthropicResponse struct {
	Content []struct {
		Type string `json:"type"`
		Text string `json:"text"`
	} `json:"content"`
	Usage struct {
		InputTokens              int `json:"input_tokens"`
		OutputTokens             int `json:"output_tokens"`
		CacheReadInputTokens     int `json:"cache_read_input_tokens"`
		CacheCreationInputTokens int `json:"cache_creation_input_tokens"`
	} `json:"usage"`
}

// Complete implements ai.Completer.
func (c *AnthropicClient) Complete(ctx context.Context, req ai.CompletionRequest) (ai.Completion, error) {
	if !c.Available() {
		return ai.Completion{}, errors.New("anthropic: missing api key")
	}

	maxTokens := req.MaxTokens
	if maxTokens <= 0 {
		maxTokens = 1024
	}

	body := anthropicRequest{
		Model:     c.model,
		MaxTokens: maxTokens,
		System:    systemBlocks(req.System),
		Messages:  toAnthropicMessages(req.Messages),
	}
	if !c.noTemperature.Load() {
		temp := req.Temperature
		body.Temperature = &temp
	}
	headers := map[string]string{
		"x-api-key":         c.apiKey,
		"anthropic-version": anthropicVersion,
	}

	var out anthropicResponse
	err := postJSON(ctx, c.http, anthropicURL, headers, body, &out)
	if err != nil && body.Temperature != nil && rejectsTemperature(err) {
		// This model (e.g. Opus 4.7+, Sonnet 5) does not accept a temperature
		// override at all. Remember that and retry once without the field.
		c.noTemperature.Store(true)
		body.Temperature = nil
		err = postJSON(ctx, c.http, anthropicURL, headers, body, &out)
	}
	if err != nil {
		return ai.Completion{}, err
	}

	usage := ai.Usage{
		InputTokens:              out.Usage.InputTokens,
		OutputTokens:             out.Usage.OutputTokens,
		CacheReadInputTokens:     out.Usage.CacheReadInputTokens,
		CacheCreationInputTokens: out.Usage.CacheCreationInputTokens,
	}
	for _, block := range out.Content {
		if block.Type == "text" && block.Text != "" {
			return ai.Completion{Text: block.Text, Usage: usage, Model: c.model}, nil
		}
	}
	return ai.Completion{}, errors.New("anthropic: empty completion")
}

// rejectsTemperature reports whether err is a 400 caused by the model refusing
// a temperature override (rather than some other bad-request cause).
func rejectsTemperature(err error) bool {
	var httpErr *httpError
	if !errors.As(err, &httpErr) || httpErr.status != http.StatusBadRequest {
		return false
	}
	return strings.Contains(httpErr.body, "temperature")
}

// systemBlocks wraps a system prompt as a single cacheable content block. An
// empty prompt yields nil, which the omitempty tag then drops from the request.
func systemBlocks(system string) []anthropicBlock {
	if system == "" {
		return nil
	}
	return []anthropicBlock{{Type: "text", Text: system, CacheControl: ephemeralCache}}
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
