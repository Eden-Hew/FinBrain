from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import TokenizedContent
from app.services.retrieval import RetrievalHit

ALLOWED_METADATA_KEYS = {
    "status",
    "due_date",
    "has_assigned_owner",
    "amount_band",
    "schema_name",
    "batch_ref",
    "has_tin",
    "currency",
}


@dataclass(frozen=True, slots=True)
class QueryFilters:
    source_systems: tuple[str, ...] = ()
    record_types: tuple[str, ...] = ()
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    categories: tuple[str, ...] = ()
    priorities: tuple[str, ...] = ()
    action_required: bool | None = None
    content_ids: tuple[int, ...] = ()
    metadata_equals: tuple[tuple[str, str], ...] = ()
    metadata_missing: tuple[str, ...] = ()

    def with_content_ids(self, content_ids: list[int]) -> "QueryFilters":
        return replace(self, content_ids=tuple(content_ids))


def eligible_statement(filters: QueryFilters) -> Select[tuple[TokenizedContent]]:
    statement = select(TokenizedContent).where(TokenizedContent.processing_status == "ready")
    if filters.source_systems:
        statement = statement.where(TokenizedContent.source_system.in_(filters.source_systems))
    if filters.record_types:
        statement = statement.where(TokenizedContent.record_type.in_(filters.record_types))
    if filters.occurred_from is not None:
        statement = statement.where(TokenizedContent.occurred_at >= filters.occurred_from)
    if filters.occurred_to is not None:
        statement = statement.where(TokenizedContent.occurred_at < filters.occurred_to)
    if filters.categories:
        statement = statement.where(
            TokenizedContent.structured_summary["category"].as_string().in_(filters.categories)
        )
    if filters.priorities:
        statement = statement.where(
            TokenizedContent.structured_summary["priority"].as_string().in_(filters.priorities)
        )
    if filters.action_required is not None:
        statement = statement.where(
            TokenizedContent.structured_summary["action_required"].as_boolean()
            == filters.action_required
        )
    if filters.content_ids:
        statement = statement.where(TokenizedContent.id.in_(filters.content_ids))
    for key, value in filters.metadata_equals:
        if key not in ALLOWED_METADATA_KEYS:
            raise ValueError("unsupported_metadata_filter")
        statement = statement.where(TokenizedContent.safe_metadata[key].as_string() == value)
    for key in filters.metadata_missing:
        if key not in ALLOWED_METADATA_KEYS:
            raise ValueError("unsupported_metadata_filter")
        statement = statement.where(TokenizedContent.safe_metadata[key].as_string().is_(None))
    return statement


def _hit(row: TokenizedContent) -> RetrievalHit:
    return RetrievalHit(
        content_id=row.id,
        source_record_id=row.source_record_id,
        source_system=row.source_system,
        record_type=row.record_type,
        occurred_at=row.occurred_at,
        protected_excerpt=row.content_text,
        protected_summary=row.summary,
        similarity=1.0,
    )


def list_eligible_hits(
    db: Session,
    filters: QueryFilters,
    *,
    limit: int | None = None,
) -> list[RetrievalHit]:
    statement = eligible_statement(filters).order_by(
        TokenizedContent.occurred_at.desc(), TokenizedContent.id.desc()
    )
    if limit is not None:
        statement = statement.limit(limit)
    return [_hit(row) for row in db.scalars(statement).all()]


def count_eligible_records(db: Session, filters: QueryFilters) -> int:
    statement = eligible_statement(filters).with_only_columns(
        func.count(TokenizedContent.id), maintain_column_froms=True
    )
    return int(db.scalar(statement) or 0)


def safe_filter_summary(filters: QueryFilters) -> dict[str, Any]:
    """Return only normalized, allowlisted filter values suitable for debug events."""
    return {
        "source_systems": list(filters.source_systems),
        "record_types": list(filters.record_types),
        "occurred_from": filters.occurred_from.isoformat() if filters.occurred_from else None,
        "occurred_to": filters.occurred_to.isoformat() if filters.occurred_to else None,
        "categories": list(filters.categories),
        "priorities": list(filters.priorities),
        "action_required": filters.action_required,
        "content_count": len(filters.content_ids),
        "metadata_equals": dict(filters.metadata_equals),
        "metadata_missing": list(filters.metadata_missing),
    }
