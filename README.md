# Sahiy Agent

**Go** AI service layer for customer support chat.

- **HTTP API** (`POST /process`) for the Go backend or any other caller
- **Telegram bot** as a customer-facing channel
- **PostgreSQL + pgvector** for sessions, messages, FAQ retrieval and tickets
- **Anthropic Claude** (`AI_PROVIDER`), falling back to a rules-based degraded mode

Schema migrations and the baseline FAQ knowledge base are applied by the
services themselves at startup. There is no separate migrate or seed step.

## Architecture

```
┌─────────────┐
│  Telegram   │──┐
└─────────────┘  │   ┌──────────────┐   ┌─────────────────┐   ┌──────────────┐
                 ├──▶│ ReplyService │──▶│ RouterResponder │──▶│  Handlers    │
┌─────────────┐  │   │  (session)   │   │    (routing)    │   │ faq / order  │
│ POST        │──┘   └──────────────┘   └─────────────────┘   │ catalog /    │
│ /process    │              │                                │ pickup /     │
└─────────────┘              ▼                                │ support      │
                    PostgreSQL + pgvector                     └──────────────┘
```

Both channels go through the same `chat.ReplyService` — one code path.

| Layer | Package | Role |
|-------|---------|------|
| Domain | `internal/domain/` | Aggregates and rules, no external dependencies |
| Application | `internal/app/` | Use cases: chat, router, faq, order, catalog, pickup, support, identity |
| Adapters | `internal/infra/` | Postgres, Sahiy API, LLM providers, embeddings, exchange rates |
| Channels | `internal/channel/` | Telegram bot |
| Transport | `internal/api/` | HTTP routes, middleware, schemas |
| Composition | `internal/platform/bootstrap/` | Wiring shared by both binaries |

Dependencies point inward: `domain` never imports `app`, `app` never imports `infra`.

## Quick start

```bash
cp .env.example .env   # fill in TELEGRAM_BOT_TOKEN, AI keys, Sahiy credentials
docker compose up -d --build
curl http://localhost:8001/health
```

Running the binaries directly against the compose Postgres (published on
`127.0.0.1:5433`):

```bash
go run ./cmd/api    # HTTP API on :8001
go run ./cmd/bot    # Telegram long-polling bot
```

## Knowledge base

The baseline FAQ ships inside the binary at
`internal/infra/persistence/postgres/seeds/faq.json` (189 entries in uz, uz-Cyrillic,
ru, en, zh) and is inserted on startup.

The seed is **insert-only**: rows that already exist are never overwritten, so
edits made in the database — and embeddings computed later — survive a restart.
Adding an entry to the JSON makes it appear on the next start.

No real embedding provider is wired up (Claude has no embedding API), so vector
search never has anything to match and retrieval falls back to lexical
(trigram) search over the knowledge base.

## Environment variables

See [.env.example](.env.example) for the full list. The ones that matter most:

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `development` | Any non-development value requires `AI_SERVICE_TOKEN` |
| `DATABASE_URL` | `postgres://…@localhost:5433/sahiy_agent` | Postgres DSN |
| `AI_SERVICE_TOKEN` | _(empty)_ | Shared secret for `POST /process` and `POST /faq`; **required outside development** |
| `AI_PROVIDER` | `auto` | `anthropic`, `rules`, or `auto` |
| `ANTHROPIC_API_KEY` | _(empty)_ | Chat provider; empty means every reply is degraded (rules fallback) |
| `RAG_SIMILARITY_THRESHOLD` | `0.85` | Minimum cosine similarity for a knowledge-base match |
| `AI_ESCALATION_THRESHOLD` | `0.45` | Replies below this confidence are handed to an operator |
| `TELEGRAM_BOT_TOKEN` | _(empty)_ | Required by `cmd/bot` |
| `TELEGRAM_WORKERS` | `32` | Updates answered concurrently |

## Learning loop

Three tables record what the assistant did and how it was received, so answer
quality can be measured instead of guessed:

| Table | One row per | Written by |
|-------|-------------|------------|
| `agent_token_usage` | LLM call | `llm.ChainedClient` (background) |
| `agent_turns` | answered message | `chat.ReplyService` (background) |
| `agent_ratings` | customer star rating | `chat.ReplyService` (inline) |

All three carry a nullable `session_id`, so they join to each other and to
`chat_sessions`. None has a foreign key: they are append-only telemetry written
off the request path and must never fail a customer reply.

`POST /faq` closes the loop — a question the assistant could not answer can be
added to the knowledge base and is retrievable on the next question, with no
embedding needed (retrieval falls back to trigram search).

## API

### `GET /health`

Unauthenticated, for probes.

```json
{"status":"ok","service":"sahiy-agent","db":"ok"}
```

### `POST /process`

Requires `X-Service-Token` when `AI_SERVICE_TOKEN` is set.

```bash
curl -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -H "X-Service-Token: $AI_SERVICE_TOKEN" \
  -d '{
    "session_id": "00000000-0000-0000-0000-000000000001",
    "user_id": "user-42",
    "text": "Yetkazib berish qancha vaqt oladi?",
    "context": {"channel": "web"}
  }'
```

```json
{
  "type": "auto",
  "text": "...",
  "confidence": 0.92,
  "escalate": false,
  "handoff_reason": null,
  "ticket_id": null
}
```

### `POST /faq`

Adds a knowledge-base entry. Requires `AI_SERVICE_TOKEN`. `question` and
`answer` are required; `locales` is optional and keyed by language code
(`uz`, `cyr`, `ru`, `en`, `zh`), each falling back to the base text.

```json
{
  "question": "Qanday qilib promokod ishlataman?",
  "answer": "Buyurtma rasmiylashtirishda promokod maydoniga kiriting.",
  "category": "orders",
  "locales": {"ru": {"question": "Как использовать промокод?", "answer": "Введите промокод при оформлении."}}
}
```

Returns `201` with `{"id": 190}`.

`escalate: true` means the assistant was not confident enough to answer alone and
the conversation should reach a human. See
[docs/GO_INTEGRATION.md](docs/GO_INTEGRATION.md) for client details and ops notes.

## Telegram bot

Set `TELEGRAM_BOT_TOKEN`, then `go run ./cmd/bot`.

Commands: `/start` (pick a language), `/new` (start a fresh conversation).

## Development

```bash
go build ./...
go vet ./...
gofmt -l internal cmd     # must print nothing
go test -race ./...
```

## Production notes

- `APP_ENV=production` refuses to start without `AI_SERVICE_TOKEN`, so the
  endpoint can never come up unauthenticated by accident.
- `LOG_JSON=true` for structured logs.
- Both binaries shut down gracefully on SIGTERM: the bot stops polling and lets
  in-flight replies finish within `TELEGRAM_SHUTDOWN_GRACE_SECONDS`.
- Expose only the Go gateway publicly; keep `:8001` on localhost behind it.

No Redis or external vector database required — only PostgreSQL with pgvector.
