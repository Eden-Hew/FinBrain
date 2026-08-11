import numpy as np
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import TokenizedContent


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
                "select content_text from tokenized_content "
                "order by embedding <=> cast(:query_embedding as extensions.vector) limit :limit"
            ),
            {"query_embedding": vector_literal, "limit": k},
        )
        return [row.content_text for row in rows]

    rows = db.scalars(select(TokenizedContent)).all()
    ranked = sorted(
        ((_cosine(query_embedding, row.embedding), row) for row in rows),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [row.content_text for score, row in ranked[:k] if score > -1.0]
