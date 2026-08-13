from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import IntegrationStatus, TokenizedContent
from app.schemas import ProtectedIngestionRecordResponse, TelegramIntegrationStatusResponse

router = APIRouter(tags=["integrations"])


@router.get(
    "/integrations/telegram/status", response_model=TelegramIntegrationStatusResponse
)
def telegram_status(db: Session = Depends(get_db)) -> TelegramIntegrationStatusResponse:
    settings = get_settings()
    row = db.get(IntegrationStatus, "telegram")
    status = "not_configured"
    if row:
        heartbeat = row.last_heartbeat_at
        if heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=UTC)
        stale = datetime.now(UTC) - heartbeat > timedelta(
            seconds=max(settings.telegram_heartbeat_seconds * 3, 90)
        )
        status = "offline" if stale else row.status
    return TelegramIntegrationStatusResponse(
        configured=bool(settings.telegram_bot_token),
        mode=settings.telegram_mode,
        status=status,
        detector_ready=bool(row and row.detector_ready),
        last_heartbeat_at=row.last_heartbeat_at if row else None,
        last_update_at=row.last_update_at if row else None,
    )


@router.get("/ingestion-records", response_model=list[ProtectedIngestionRecordResponse])
def ingestion_records(
    source_system: str = Query("telegram", pattern=r"^[a-z0-9_.-]+$"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[ProtectedIngestionRecordResponse]:
    rows = db.scalars(
        select(TokenizedContent)
        .where(TokenizedContent.source_system == source_system)
        .order_by(TokenizedContent.created_at.desc())
        .limit(limit)
    ).all()
    return [
        ProtectedIngestionRecordResponse(
            source_record_id=row.source_record_id,
            source_system=row.source_system,
            record_type=row.record_type,
            content_excerpt=row.content_text[:500],
            summary=row.summary,
            structured_summary=row.structured_summary,
            processing_status=row.processing_status,
            enrichment_mode=row.enrichment_mode,
            occurred_at=row.occurred_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
            safe_metadata=row.safe_metadata,
        )
        for row in rows
    ]
