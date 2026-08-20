# syntax=docker/dockerfile:1

# Build stage: resolve and install dependencies into a venv.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/uv.lock backend/pyproject.toml ./

# Install the backend deps but exclude torch, its Linux-only CUDA dependencies
# (nvidia-*, cuda-*, triton), and opencv-python. The app runs GLiNER/OCR on CPU,
# so the CUDA libraries are dead weight (~2.5 GB), and the headless OpenCV build
# avoids the mesa/LLVM GL libraries the full build requires. Both are replaced
# with leaner equivalents right after.
RUN set -eux; \
    EXCLUDED="torch triton opencv-python \
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
    --index-strategy unsafe-best-match \
    "torch==2.13.0+cpu" \
    "opencv-python-headless>=5,<6"

COPY backend/app ./app
COPY backend/scripts ./scripts
COPY backend/seed ./seed

# Runtime stage: lean image with only what runs the API and workers.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    MALLOC_ARENA_MAX=2 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    TOKENIZERS_PARALLELISM=false

COPY --from=build /app/.venv ./.venv
COPY --from=build /app/app ./app
COPY --from=build /app/scripts ./scripts
COPY --from=build /app/seed ./seed

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
