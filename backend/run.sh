#!/usr/bin/env bash
# TG Glance backend. Demo mode by default (no Telegram connection, sends
# go to outbox.jsonl). Live mode: TELEGRAM_LIVE=1 SEND_ENABLED=1.
set -euo pipefail
cd "$(dirname "$0")"
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8787
