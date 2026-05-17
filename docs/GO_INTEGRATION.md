# Go backend integration

Python AI service runs on `localhost:8001`. Go gateway calls it after saving the user message.

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
    "locale": "uz"
  }
}
```

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

    resp, err := c.http.Do(httpReq) // Client.Timeout = 30 * time.Second
    // handle resp...
}
```

## Tool call endpoint (Go → Python → Go)

When classifier returns `api`, Python calls:

`POST {GO_BACKEND_URL}/internal/ai/order-lookup`

Implement this on Go side, or rely on mock data until ready.

## Operations

| Protection            | Where        | Value        |
|-----------------------|-------------|--------------|
| User rate limit       | Go middleware | 20 req/hour |
| GPT concurrency       | Python semaphore | 10       |
| Upstream timeout      | Go → Python | 30s          |
| GPT timeout           | Python      | 30s (`AI_TIMEOUT_SECONDS`) |

## Production

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 2
```

Set `LOG_JSON=true` for structured logs. Bind to localhost only; Nginx/Go faces the public internet.
