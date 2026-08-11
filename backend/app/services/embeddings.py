import hashlib
import math
import re

from app.config import get_settings
from app.security.detect import contains_known_pii


def _offline_embedding(text: str, dimensions: int = 128) -> list[float]:
    """Deterministic feature-hashing fallback for local demonstrations."""
    vector = [0.0] * dimensions
    for word in re.findall(r"[A-Za-z0-9_]+", text.casefold()):
        digest = hashlib.sha256(word.encode()).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += -1.0 if digest[4] & 1 else 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def embed_text(text: str) -> tuple[list[float], str]:
    if contains_known_pii(text):
        raise ValueError("Refusing to embed text containing recognized PII")
    settings = get_settings()
    if settings.gemini_api_key:
        try:
            from google import genai

            client = genai.Client(api_key=settings.gemini_api_key)
            result = client.models.embed_content(
                model=settings.gemini_embedding_model,
                contents=text,
                config={"output_dimensionality": 768},
            )
            return list(result.embeddings[0].values), "gemini"
        except Exception:
            if not settings.allow_offline_demo:
                raise
    if not settings.allow_offline_demo:
        raise RuntimeError("GEMINI_API_KEY is required when offline demo mode is disabled")
    return _offline_embedding(text), "offline-demo"
