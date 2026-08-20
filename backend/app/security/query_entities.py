import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ProtectedTokenRegistry
from app.security.detect import Span
from app.security.tokenize import derive_token

_WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9'.-]*")
_BOUNDARY_WORDS = {
    "a",
    "about",
    "all",
    "an",
    "and",
    "customer",
    "customers",
    "describe",
    "detail",
    "details",
    "find",
    "for",
    "information",
    "list",
    "me",
    "of",
    "on",
    "please",
    "show",
    "tell",
    "the",
    "with",
}
_ENTITY_TYPES = ("PERSON", "ORG")
_MAX_ENTITY_WORDS = 5


def _candidate_spans(text: str) -> list[tuple[int, int, str]]:
    """Return plausible entity phrases; registry confirmation prevents guessing."""
    words = list(_WORD_PATTERN.finditer(text))
    runs: list[list[re.Match[str]]] = []
    current: list[re.Match[str]] = []
    for word in words:
        if word.group().casefold() in _BOUNDARY_WORDS:
            if current:
                runs.append(current)
                current = []
            continue
        current.append(word)
    if current:
        runs.append(current)

    candidates: list[tuple[int, int, str]] = []
    for run in runs:
        for width in range(min(_MAX_ENTITY_WORDS, len(run)), 0, -1):
            for start_index in range(0, len(run) - width + 1):
                selected = run[start_index : start_index + width]
                start, end = selected[0].start(), selected[-1].end()
                candidates.append((start, end, text[start:end]))
    return candidates


def resolve_registered_entity_spans(
    db: Session,
    text: str,
    tenant_id: str,
    existing_spans: list[Span],
) -> list[Span]:
    """Resolve query entities against tenant token metadata, never vault plaintext."""
    token_candidates: dict[str, tuple[int, int, str, str]] = {}
    for start, end, value in _candidate_spans(text):
        for entity_type in _ENTITY_TYPES:
            token_candidates[derive_token(entity_type, value, tenant_id)] = (
                start,
                end,
                value,
                entity_type,
            )
    if not token_candidates:
        return existing_spans

    registered = set(
        db.scalars(
            select(ProtectedTokenRegistry.token).where(
                ProtectedTokenRegistry.tenant_id == tenant_id,
                ProtectedTokenRegistry.token.in_(token_candidates),
            )
        ).all()
    )
    # Deterministic regex spans remain highest priority. A tenant-confirmed registry
    # match outranks GLiNER because the latter may over-extend a name into a following
    # query word such as "contact".
    resolved = [span for span in existing_spans if span.source == "regex"]
    matches = sorted(
        (token_candidates[token] for token in registered),
        key=lambda item: (-(item[1] - item[0]), item[0]),
    )
    for start, end, value, entity_type in matches:
        if any(start < span.end and span.start < end for span in resolved):
            continue
        label = "person" if entity_type == "PERSON" else "company name"
        resolved.append(Span(start, end, value, label, "token-registry"))
    for span in existing_spans:
        if span.source == "regex":
            continue
        if not any(span.start < current.end and current.start < span.end for current in resolved):
            resolved.append(span)
    return sorted(resolved, key=lambda span: span.start)
