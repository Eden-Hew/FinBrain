from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import TokenizedContent

if TYPE_CHECKING:
    from app.services.query_filters import QueryFilters


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    content_id: int
    source_record_id: str
    source_system: str
    record_type: str | None
    occurred_at: datetime | None
    protected_excerpt: str
    protected_summary: str | None
    similarity: float

    @property
    def retrieval_text(self) -> str:
        return _retrieval_text(self.protected_excerpt, self.protected_summary)


def _retrieval_text(content_text: str, summary: str | None) -> str:
    if not summary:
        return content_text
    return f"Protected summary: {summary}\nProtected source: {content_text}"


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return -1.0
    a, b = np.asarray(left), np.asarray(right)
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denominator) if denominator else 0.0


def _hit_from_row(row: TokenizedContent, similarity: float) -> RetrievalHit:
    return RetrievalHit(
        content_id=row.id,
        source_record_id=row.source_record_id,
        source_system=row.source_system,
        record_type=row.record_type,
        occurred_at=row.occurred_at,
        protected_excerpt=row.content_text,
        protected_summary=row.summary,
        similarity=similarity,
    )


def retrieve_hits(
    db: Session,
    query_embedding: list[float],
    k: int = 5,
    *,
    filters: "QueryFilters | None" = None,
) -> list[RetrievalHit]:
    # Local import: query_filters imports RetrievalHit from this module, so a
    # top-level import here would be circular. QueryFilters() is a cheap default
    # (DEFAULT_TENANT_ID, no other filters) matching this function's old signature.
    from app.services.query_filters import QueryFilters, apply_content_filters

    filters = filters or QueryFilters()

    if db.bind is not None and db.bind.dialect.name == "postgresql":
        vector_literal = "[" + ",".join(str(value) for value in query_embedding) + "]"
        distance_sql = (
            "tokenized_content.embedding <=> cast(:query_embedding as extensions.vector)"
        )
        statement = (
            apply_content_filters(select(TokenizedContent), filters)
            .where(TokenizedContent.embedding.is_not(None))
            .add_columns(text(f"1 - ({distance_sql})").label("similarity"))
            .order_by(text(distance_sql))
            .limit(k)
        )
        rows = db.execute(statement, {"query_embedding": vector_literal}).all()
        return [_hit_from_row(row.TokenizedContent, float(row.similarity)) for row in rows]

    statement = apply_content_filters(select(TokenizedContent), filters).where(
        TokenizedContent.embedding.is_not(None)
    )
    rows = db.scalars(statement).all()
    ranked = sorted(
        ((_cosine(query_embedding, row.embedding), row) for row in rows),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [_hit_from_row(row, score) for score, row in ranked[:k] if score > -1.0]


def retrieve_top_k(db: Session, query_embedding: list[float], k: int = 5) -> list[str]:
    """Compatibility API returning protected text rather than structured evidence."""
    return [hit.retrieval_text for hit in retrieve_hits(db, query_embedding, k)]
