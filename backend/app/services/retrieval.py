import numpy as np
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import TokenizedContent


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


def retrieve_top_k(db: Session, query_embedding: list[float], k: int = 5) -> list[str]:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        vector_literal = "[" + ",".join(str(value) for value in query_embedding) + "]"
        rows = db.execute(
            text(
                "select content_text, summary from tokenized_content "
                "where embedding is not null "
                "order by embedding <=> cast(:query_embedding as extensions.vector) limit :limit"
            ),
            {"query_embedding": vector_literal, "limit": k},
        )
        return [_retrieval_text(row.content_text, row.summary) for row in rows]

    rows = db.scalars(select(TokenizedContent).where(TokenizedContent.embedding.is_not(None))).all()
    ranked = sorted(
        ((_cosine(query_embedding, row.embedding), row) for row in rows),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [
        _retrieval_text(row.content_text, row.summary) for score, row in ranked[:k] if score > -1.0
    ]
