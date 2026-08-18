#!/bin/sh
set -eu

cd /app

# Run an optional worker with an auto-restart loop so a transient crash does not
# take down the container. Each worker logs its start/exit transitions to the
# container stdout, which Railway surfaces in its deploy logs.
start_worker() {
  name="$1"
  shift
  while :; do
    echo "[entrypoint] starting $name worker"
    if "$@"; then
      echo "[entrypoint] $name worker exited normally, restarting in 3s"
    else
      echo "[entrypoint] $name worker exited with code $?, restarting in 3s"
    fi
    sleep 3
  done &
}

if [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
  start_worker "telegram" python -m app.integrations.telegram.runner
fi

if [ "${EMAIL_CONNECTOR_ENABLED:-}" = "true" ]; then
  start_worker "email" python -m app.integrations.email_connector.runner
fi

if [ "${VAULT_AUTO_ROTATION_ENABLED:-}" = "true" ]; then
  start_worker "vault-rotation" python -m app.security.rotation_runner
fi

cleanup() {
  trap - TERM INT
  jobs -p | xargs -r kill 2>/dev/null || true
}
trap cleanup TERM INT

echo "[entrypoint] starting API on 0.0.0.0:${PORT:-8000}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
