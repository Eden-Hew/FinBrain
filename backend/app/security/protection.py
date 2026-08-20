from sqlalchemy.orm import Session

from app.models import TokenVaultEntry
from app.security.detect import contains_known_pii, detect_spans
from app.security.tokenize import tokenize_record


def protect_text(
    text: str, source_record_id: str, tenant_id: str, db: Session | None = None
) -> tuple[str, list[TokenVaultEntry]]:
    protected, entries = tokenize_record(
        text, detect_spans(text), source_record_id, tenant_id, db=db
    )
    if contains_known_pii(protected):
        raise ValueError(f"Safety-net PII detection failed for source {source_record_id}")
    return protected, entries


def protect_metadata(
    metadata: dict[str, str], source_record_id: str, tenant_id: str,
    db: Session | None = None,
) -> tuple[dict[str, str], list[TokenVaultEntry]]:
    protected_metadata: dict[str, str] = {}
    entries: dict[str, TokenVaultEntry] = {}
    for key, value in metadata.items():
        protected_value, value_entries = protect_text(value, source_record_id, tenant_id, db)
        protected_metadata[key] = protected_value
        entries.update({entry.token: entry for entry in value_entries})
    return protected_metadata, list(entries.values())
