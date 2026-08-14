from dataclasses import dataclass
from datetime import datetime

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import TokenizedContent


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


def retrieve_hits(
    db: Session,
    query_embedding: list[float],
    k: int = 5,
    *,
    source_systems: list[str] | None = None,
) -> list[RetrievalHit]:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        vector_literal = "[" + ",".join(str(value) for value in query_embedding) + "]"
        source_filter = ""
        parameters: dict[str, object] = {"query_embedding": vector_literal, "limit": k}
        if source_systems:
            source_filter = "and source_system = any(:source_systems) "
            parameters["source_systems"] = source_systems
        query = (
                "select id, source_record_id, source_system, record_type, occurred_at, "
                "content_text, summary, "
                "1 - (embedding <=> cast(:query_embedding as extensions.vector)) "
                "as similarity from tokenized_content "
                "where embedding is not null "
                + source_filter
                + "order by embedding <=> cast(:query_embedding as extensions.vector) "
                "limit :limit"
        )
        rows = db.execute(text(query), parameters)
        return [
            RetrievalHit(
                content_id=row.id,
                source_record_id=row.source_record_id,
                source_system=row.source_system,
                record_type=row.record_type,
                occurred_at=row.occurred_at,
                protected_excerpt=row.content_text,
                protected_summary=row.summary,
                similarity=float(row.similarity),
            )
            for row in rows
        ]

    statement = select(TokenizedContent).where(TokenizedContent.embedding.is_not(None))
    if source_systems:
        statement = statement.where(TokenizedContent.source_system.in_(source_systems))
    rows = db.scalars(statement).all()
    ranked = sorted(
        ((_cosine(query_embedding, row.embedding), row) for row in rows),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [
        RetrievalHit(
            content_id=row.id,
            source_record_id=row.source_record_id,
            source_system=row.source_system,
            record_type=row.record_type,
            occurred_at=row.occurred_at,
            protected_excerpt=row.content_text,
            protected_summary=row.summary,
            similarity=score,
        )
        for score, row in ranked[:k]
        if score > -1.0
    ]


def retrieve_top_k(db: Session, query_embedding: list[float], k: int = 5) -> list[str]:
    """Compatibility API returning protected text rather than structured evidence."""
    return [hit.retrieval_text for hit in retrieve_hits(db, query_embedding, k)]
