import hashlib
import math
import re
from collections import OrderedDict

from app.config import get_settings
from app.security.detect import contains_known_pii
from app.services.gemini import gemini_client

# Matches the pgvector column width (vector(768)) so the offline fallback stays a
# valid drop-in for real HNSW similarity search, not just SQLite's Python-side cosine.
EMBEDDING_DIMENSIONS = 768


def _offline_embedding(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
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
            client = gemini_client()
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


_QUERY_EMBEDDING_CACHE_SIZE = 256
_query_embedding_cache: OrderedDict[str, tuple[list[float], str]] = OrderedDict()


def embed_query_cached(text: str) -> tuple[list[float], str]:
    """In-process LRU cache for query-time embeddings.

    Chat questions repeat often within a session; this avoids re-embedding an
    identical sanitized question. Per-process only (no cross-instance sharing) --
    the cheap first cut called out in the roadmap, not a durability guarantee.
    """
    cached = _query_embedding_cache.get(text)
    if cached is not None:
        _query_embedding_cache.move_to_end(text)
        return cached
    result = embed_text(text)
    _query_embedding_cache[text] = result
    if len(_query_embedding_cache) > _QUERY_EMBEDDING_CACHE_SIZE:
        _query_embedding_cache.popitem(last=False)
    return result
