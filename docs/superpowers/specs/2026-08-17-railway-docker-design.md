# Railway Docker Deployment for FinBrain Backend

Date: 2026-08-17

## Problem

Deploy the FinBrain backend (FastAPI API + optional Telegram and email workers) to Railway using a
Docker image. The frontend is deployed separately to Vercel (out of scope for this spec). The
local launcher `scripts/run_demo.ps1` is Windows PowerShell and cannot run inside a Linux Railway
container; the container mirrors its component set with a Linux entrypoint.

## Goal

A single Railway service that runs:
- FastAPI backend (`uvicorn app.main:app`) as the foreground process on the Railway-provided
  `PORT`, with `/health` as the healthcheck.
- Telegram long-polling worker when `TELEGRAM_BOT_TOKEN` is set.
- Email polling worker when `EMAIL_CONNECTOR_ENABLED=true`.

## Scope

New files at repo root:
- `Dockerfile`
- `.dockerignore`
- `docker/entrypoint.sh`
- `railway.json`

No changes to application code. `run_demo.ps1` remains the Windows local launcher.

## Dockerfile

- Base: `ghcr.io/astral-sh/uv:python3.13-bookworm-slim` (uv baked in, matches local Python 3.13).
- Apt deps: `libgomp1` (torch), `libgl1` + `libglib2.0-0` (opencv-python pulled by RapidOCR), and
  `curl` for optional debug.
- Copy `backend/uv.lock` + `backend/pyproject.toml` and run `uv sync --frozen --no-install-project
  --no-install-package torch`, then install a CPU-only torch from the PyTorch CPU index so the image
  does not ship CUDA libraries (GLiNER/OCR run on CPU). After copying the source, a second
  `uv sync --frozen --no-install-package torch` installs the project itself.
- Runtime command is provided by `docker/entrypoint.sh`.

## Entrypoint (`docker/entrypoint.sh`)

```sh
#!/bin/sh
set -eu

cd /app
# optional workers
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
  python -m app.integrations.telegram.runner &
fi
if [ "${EMAIL_CONNECTOR_ENABLED:-}" = "true" ]; then
  python -m app.integrations.email_connector.runner &
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
```

Workers run as background jobs; uvicorn is PID 1 so Railway health/lifecycle signals target it.

## railway.json

- `builder`: `DOCKERFILE`
- `dockerfilePath`: `Dockerfile`
- `healthcheckPath`: `/health`
- `healthcheckTimeout`: 300 (first boot downloads GLiNER model)
- `restartPolicyType`: `ON_FAILURE`

## Configuration

All settings come from Railway environment variables (no `.env` file in the image):
`DATABASE_URL`, `TOKEN_ROOT_SECRET`, `SUPABASE_URL`, `SUPABASE_JWT_*`, `GEMINI_API_KEY`,
`MORPHEUS_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OPERATOR_ROLES`, `EMAIL_CONNECTOR_ENABLED`,
`EMAIL_IMAP_*`, and OCR/GliNER toggles as needed.

## Out of scope

- Frontend / Vercel deployment.
- Database migrations and seeding (performed against Supabase as today).
- Multi-worker uvicorn scaling.