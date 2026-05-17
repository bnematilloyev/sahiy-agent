# Sahiy Agent

Pluggable **Python AI service layer** for customer support chat.

- **FastAPI** HTTP API (`POST /process`) for Go or any backend
- **Telegram bot** for local testing
- **PostgreSQL + pgvector** for sessions, messages, FAQ RAG, tickets
- **OpenAI GPT** or **Anthropic Claude** (switch via `AI_PROVIDER`), rule-based fallback

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐     ┌──────────┐
│  Telegram   │────▶│ ChatService │────▶│ ReplyService │────▶│ Handlers │
│  (test)     │     │  (session)  │     │   (intent)   │     │ faq/order│
└─────────────┘     └──────┬──────┘     └──────────────┘     │ /support │
┌─────────────┐            │                                  └──────────┘
│ Go :8080    │──POST /process (same ChatService)
└─────────────┘            ▼
                    PostgreSQL + pgvector
```

Both **Telegram** and **`POST /process`** call `ChatService.reply()` — one code path.

| Layer | Package | Role |
|-------|---------|------|
| API | `app/api/` | HTTP routes, middleware, schemas |
| Channels | `app/channels/` | Telegram bot |
| Services | `app/services/` | `ChatService`, `ReplyService`, `IntentService`, `FaqService` |
| Handlers | `app/handlers/` | FAQ / order / support reply logic |
| Repositories | `app/repositories/` | DB access |
| Infrastructure | `app/infrastructure/` | GPT (OpenAI), embedder, order API |

## Quick start

```bash
cp .env.example .env
docker compose up -d
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python scripts/seed_faq.py --clear
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
curl http://localhost:8001/health
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...@localhost:5433/sahiy_agent` | Async Postgres URL |
| `AI_PROVIDER` | `auto` | `openai`, `anthropic`, `rules`, or `auto` |
| `OPENAI_API_KEY` | _(empty)_ | GPT + embeddings |
| `OPENAI_MODEL` | `gpt-4o-mini` | GPT chat model |
| `ANTHROPIC_API_KEY` | _(empty)_ | Claude chat |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Claude model |
| `EMBEDDING_PROVIDER` | `auto` | `openai` or `mock` |
| `AI_MAX_CONCURRENT` | `10` | Max parallel AI calls |
| `AI_TIMEOUT_SECONDS` | `30` | Per-request timeout |
| `RAG_SIMILARITY_THRESHOLD` | `0.85` | Min cosine similarity for FAQ match |
| `RAG_TOP_K` | `3` | Max FAQ chunks retrieved |
| `GO_BACKEND_URL` | `http://localhost:8080` | Go tool-call base URL |
| `TELEGRAM_BOT_TOKEN` | _(empty)_ | Required for Telegram bot |
| `LOG_JSON` | `false` | `true` for JSON logs in production |
| `LOG_LEVEL` | `INFO` | Logging level |

## API

### `GET /health`

```json
{"status":"ok","app":"sahiy-agent","version":"0.1.0","database":"connected"}
```

### `POST /process`

```bash
curl -X POST http://localhost:8001/process \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: my-trace-id" \
  -d '{
    "session_id": "00000000-0000-0000-0000-000000000001",
    "user_id": "user-42",
    "text": "Yetkazib berish qancha vaqt oladi?",
    "context": {"channel": "web"}
  }'
```

Response:

```json
{
  "type": "auto",
  "text": "...",
  "ticket_id": null
}
```

See [docs/GO_INTEGRATION.md](docs/GO_INTEGRATION.md) for Go client example and ops notes.

## Telegram bot (test UI)

```bash
pip install -e ".[telegram,dev]"
# set TELEGRAM_BOT_TOKEN in .env
python scripts/run_telegram_bot.py
```

Commands: `/start`, `/new`, then send text messages.

## Tests

```bash
pytest tests/ -q
```

## Production (VPS)

```bash
# PostgreSQL with pgvector on same host
alembic upgrade head
python scripts/seed_faq.py --clear

# 2–4 workers per architecture spec
LOG_JSON=true uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 2
```

- Go gateway: public `:8080`, rate limit **20 req/hour/user**
- Python: localhost `:8001` only
- Nginx: SSL termination in front of Go

## Plug into another project

1. Run this service (HTTP on `:8001`).
2. From your app, `POST /process` with `session_id`, `user_id`, `text`, `context`.
3. Map `type` + `text` (+ `ticket_id`) to your chat UI.
4. Optionally implement `POST /internal/ai/order-lookup` on your backend for `api` routes.

No Redis or external vector DB required — only PostgreSQL.

## Project scripts

| Script | Purpose |
|--------|---------|
| `scripts/seed_faq.py --clear` | Load Uzbek FAQ embeddings |
| `scripts/run_telegram_bot.py` | Start Telegram polling bot |
