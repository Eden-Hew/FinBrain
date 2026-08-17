#!/bin/sh
set -eu

cd /app

# Optional Telegram long-polling worker, mirroring run_demo.ps1's component set.
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
  echo "[entrypoint] starting telegram worker"
  python -m app.integrations.telegram.runner &
fi

# Optional email polling worker.
if [ "${EMAIL_CONNECTOR_ENABLED:-}" = "true" ]; then
  echo "[entrypoint] starting email worker"
  python -m app.integrations.email_connector.runner &
fi

echo "[entrypoint] starting API on 0.0.0.0:${PORT:-8000}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"