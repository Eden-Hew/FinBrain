from collections.abc import Sequence
from typing import Any

import httpx

from app.config import get_settings


def morpheus_chat(
    messages: Sequence[dict[str, str]], *, temperature: float = 0.1
) -> str:
    settings = get_settings()
    if not settings.morpheus_api_key:
        raise RuntimeError("MORPHEUS_API_KEY is not configured")

    response = httpx.post(
        f"{settings.morpheus_base_url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.morpheus_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.morpheus_model,
            "messages": list(messages),
            "temperature": temperature,
            "stream": False,
        },
        timeout=90.0,
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    content = payload["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Morpheus returned an empty response")
    return content.strip()
