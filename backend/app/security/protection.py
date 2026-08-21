import re

from sqlalchemy.orm import Session

from app.models import TokenVaultEntry
from app.security.detect import Span, contains_known_pii, detect_spans
from app.security.tokenize import tokenize_record

_PROTECTED_TOKEN_PATTERN = re.compile(
    r"(?:AMOUNT_BAND_\d+_[0-9a-f]{10}|[A-Z]+_[0-9a-f]{10})"
)


def _exclude_existing_protected_tokens(text: str, spans: list[Span]) -> list[Span]:
    token_ranges = [match.span() for match in _PROTECTED_TOKEN_PATTERN.finditer(text)]
    return [
        span
        for span in spans
        if not any(
            span.start < token_end and span.end > token_start
            for token_start, token_end in token_ranges
        )
    ]


def protect_text(
    text: str,
    source_record_id: str,
    tenant_id: str,
    db: Session | None = None,
    *,
    spans: list[Span] | None = None,
    tokenizer=None,
) -> tuple[str, list[TokenVaultEntry]]:
    tokenize = tokenizer or tokenize_record
    detected_spans = detect_spans(text) if spans is None else spans
    if spans is None:
        detected_spans = _exclude_existing_protected_tokens(text, detected_spans)
    protected, entries = tokenize(
        text,
        detected_spans,
        source_record_id,
        tenant_id,
        db=db,
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
