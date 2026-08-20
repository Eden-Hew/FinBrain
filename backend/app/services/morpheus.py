from collections.abc import Sequence
from functools import lru_cache
from typing import Any

import httpx

from app.config import get_settings


@lru_cache(maxsize=2)
def _client(base_url: str, api_key: str, timeout_seconds: int) -> httpx.Client:
    return httpx.Client(
        base_url=base_url.rstrip("/"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=float(timeout_seconds),
    )


def morpheus_chat(
    messages: Sequence[dict[str, str]],
    *,
    temperature: float = 0.1,
    timeout_seconds: int | None = None,
) -> str:
    settings = get_settings()
    if not settings.morpheus_api_key:
        raise RuntimeError("MORPHEUS_API_KEY is not configured")

    response = _client(
        settings.morpheus_base_url,
        settings.morpheus_api_key,
        timeout_seconds or settings.morpheus_timeout_seconds,
    ).post(
        "/chat/completions",
        json={
            "model": settings.morpheus_model,
            "messages": list(messages),
            "temperature": temperature,
            "stream": False,
        },
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    content = payload["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Morpheus returned an empty response")
    return content.strip()
