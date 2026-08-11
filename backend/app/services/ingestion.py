from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TokenizedContent, TokenVaultEntry
from app.security.detect import contains_known_pii, detect_spans
from app.security.tokenize import tokenize_record
from app.services.embeddings import embed_text


def ingest_record(db: Session, source_id: str, source_type: str, raw_text: str) -> str:
    """Tokenize raw text in memory and persist only its sanitized representation."""
    existing = db.scalar(
        select(TokenizedContent).where(TokenizedContent.source_record_id == source_id)
    )
    if existing:
        return existing.content_text
    sanitized, entries = tokenize_record(raw_text, detect_spans(raw_text), source_id)
    if contains_known_pii(sanitized):
        raise ValueError(f"Safety-net PII detection failed for source {source_id}")
    for entry in entries:
        if db.get(TokenVaultEntry, entry.token) is None:
            db.add(entry)
    embedding, _ = embed_text(sanitized)
    db.add(
        TokenizedContent(
            source_record_id=source_id,
            content_text=sanitized,
            embedding=embedding,
            record_type=source_type,
        )
    )
    db.commit()
    return sanitized
