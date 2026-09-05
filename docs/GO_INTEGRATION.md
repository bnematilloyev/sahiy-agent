# Go backend integration

The sahiy-agent service runs on `localhost:8001`. The Go gateway calls it after saving the user message.

## Request flow

```
Client → POST /chat/message (Go :8080)
           → save message to PostgreSQL
           → POST http://127.0.0.1:8001/process (timeout 30s)
           → return response to client
```

## HTTP contract

**POST** `/process`

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "42",
  "text": "Buyurtmam qayerda?",
  "context": {
    "channel": "web",
    "reply_language": "uz"
  }
}
```

### `context` fields

| Key | Effect |
|-----|--------|
| `channel` | Stored on the session; defaults to `api`. |
| `reply_language` | Preferred reply language: `uz`, `cyr`, `ru`, `en`, `zh`. A **hint** only — if the customer's own message is clearly in another language, that wins. `locale` is accepted as an alias. |

Everything else in `context` is passed through untouched and may carry identity
markers (see the identity gate).

**Response 200**

```json
{
  "type": "auto",
  "text": "...",
  "ticket_id": null
}
```

| `type`   | Meaning                                      |
|----------|----------------------------------------------|
| `auto`   | FAQ / RAG answer                             |
| `api`    | Answer uses live data from Go APIs           |
| `ticket` | Operator ticket created; `ticket_id` is set  |

**Errors** — JSON body `{ "error", "message", "request_id" }`, status `503` for LLM/DB issues.

## Go example

```go
type ProcessRequest struct {
    SessionID string                 `json:"session_id"`
    UserID    string                 `json:"user_id"`
    Text      string                 `json:"text"`
    Context   map[string]interface{} `json:"context"`
}

type ProcessResponse struct {
    Type     string  `json:"type"`
    Text     string  `json:"text"`
    TicketID *string `json:"ticket_id"`
}

func (c *AIClient) Process(ctx context.Context, req ProcessRequest) (*ProcessResponse, error) {
    body, _ := json.Marshal(req)
    httpReq, _ := http.NewRequestWithContext(
        ctx, http.MethodPost,
        c.baseURL+"/process",
        bytes.NewReader(body),
    )
    httpReq.Header.Set("Content-Type", "application/json")
    httpReq.Header.Set("X-Request-ID", requestIDFromCtx(ctx))
    httpReq.Header.Set("X-Service-Token", c.serviceToken) // must match AI_SERVICE_TOKEN

    resp, err := c.http.Do(httpReq) // Client.Timeout = 30 * time.Second
    // handle resp...
}
```

## Order lookups

When the router returns `api`, the agent resolves order data by calling the
Sahiy Laravel API directly with its own service-user credentials. The gateway
does not need to implement anything for this.

`GO_BACKEND_URL` is a legacy setting from an earlier design where the agent
called back into the gateway; it is unused on the order path.

## Operations

| Protection            | Where        | Value        |
|-----------------------|-------------|--------------|
| User rate limit       | Go middleware | 20 req/hour |
| Upstream timeout      | Go gateway → agent | 30s   |
| LLM timeout           | agent       | 30s (`AI_TIMEOUT_SECONDS`) |

## Production

```bash
docker compose up -d --build     # or: go run ./cmd/api
```

Set `LOG_JSON=true` for structured logs. Bind to localhost only; Nginx / the Go gateway faces the public internet.
