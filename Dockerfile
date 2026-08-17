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

# Install the backend deps but exclude torch and its Linux-only CUDA
# dependencies (nvidia-*, cuda-*, triton). The app runs GLiNER/OCR on CPU, so
# those CUDA libraries are dead weight (~2.5 GB). CPU-only torch is installed
# from PyTorch's CPU index right after.
RUN set -eux; \
    EXCLUDED="torch triton \
      cuda-bindings cuda-pathfinder cuda-toolkit \
      nvidia-cublas nvidia-cuda-cupti nvidia-cuda-nvrtc nvidia-cuda-runtime \
      nvidia-cudnn-cu13 nvidia-cufft nvidia-cufile nvidia-curand nvidia-cusolver \
      nvidia-cusparse nvidia-cusparselt-cu13 nvidia-nccl-cu13 nvidia-nvjitlink \
      nvidia-nvshmem-cu13 nvidia-nvtx"; \
    ARGS=""; \
    for p in $EXCLUDED; do ARGS="$ARGS --no-install-package $p"; done; \
    uv sync --frozen --no-install-project $ARGS

RUN uv pip install \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple \
    "torch>=2.5,<3"

COPY backend/app ./app
COPY backend/scripts ./scripts
COPY backend/seed ./seed

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]