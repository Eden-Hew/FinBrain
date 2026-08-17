# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS base

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/uv.lock backend/pyproject.toml ./
# --no-install-package torch defers torch to the CPU-only index below, so the
# image does not ship CUDA libraries (the app runs GLiNER/OCR on CPU).
RUN uv sync --frozen --no-install-project --no-install-package torch
RUN uv pip install \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple \
    "torch>=2.5,<3"

COPY backend/app ./app
COPY backend/scripts ./scripts
COPY backend/seed ./seed
RUN uv sync --frozen --no-install-package torch

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]