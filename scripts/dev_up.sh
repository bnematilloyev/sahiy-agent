#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Docker (Postgres + pgvector)"
docker compose up -d

echo "==> Python dependencies"
pip install -q -e ".[telegram,dev]"

echo "==> Database migrations"
alembic upgrade head

echo "==> FAQ seed"
python scripts/seed_faq.py --clear

echo "==> Tests"
pytest tests/ -q

echo "==> API (port 8001)"
pkill -f "uvicorn app.main:app" 2>/dev/null || true
nohup uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload > /tmp/sahiy-agent-api.log 2>&1 &
sleep 2
curl -sf http://127.0.0.1:8001/health | python3 -m json.tool

if grep -q '^TELEGRAM_BOT_TOKEN=.\+' .env 2>/dev/null; then
  echo "==> Telegram bot"
  pkill -f "scripts/run_telegram_bot.py" 2>/dev/null || true
  nohup python scripts/run_telegram_bot.py > /tmp/sahiy-agent-telegram.log 2>&1 &
  echo "Telegram bot started (log: /tmp/sahiy-agent-telegram.log)"
else
  echo "Skip Telegram: set TELEGRAM_BOT_TOKEN in .env"
fi

echo ""
echo "Ready:"
echo "  API:      http://localhost:8001/health"
echo "  Process:  POST http://localhost:8001/process"
echo "  API log:  /tmp/sahiy-agent-api.log"
