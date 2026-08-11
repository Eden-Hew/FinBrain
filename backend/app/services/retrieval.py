import json

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TokenizedContent


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return -1.0
    a, b = np.asarray(left), np.asarray(right)
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denominator) if denominator else 0.0


def retrieve_top_k(db: Session, query_embedding: list[float], k: int = 5) -> list[str]:
    rows = db.scalars(select(TokenizedContent)).all()
    ranked = sorted(
        ((_cosine(query_embedding, json.loads(row.embedding)), row) for row in rows),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [row.content_text for score, row in ranked[:k] if score > -1.0]
