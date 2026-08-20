from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, require_roles
from app.auth.principal import AuthPrincipal
from app.config import get_settings
from app.db import get_db
from app.integrations.email_connector.service import get_state, sync_mailbox
from app.models import IntegrationStatus, TokenizedContent
from app.schemas import (
    EmailIntegrationStatusResponse,
    EmailSyncResponse,
    ProtectedIngestionRecordResponse,
    TelegramIntegrationStatusResponse,
    UserRole,
)
from app.services.health import heartbeat_key

router = APIRouter(tags=["integrations"])


@router.get(
    "/integrations/telegram/status", response_model=TelegramIntegrationStatusResponse
)
def telegram_status(
    _principal: AuthPrincipal = Depends(
        require_roles(UserRole.FINANCE_OPS, UserRole.OWNER_DIRECTOR, UserRole.COMPLIANCE)
    ),
    db: Session = Depends(get_db),
) -> TelegramIntegrationStatusResponse:
    settings = get_settings()
    row = db.get(
        IntegrationStatus,
        heartbeat_key(settings.effective_service_instance_id, "telegram"),
    )
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
    _principal: CurrentUser,
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


@router.get("/integrations/email/status", response_model=EmailIntegrationStatusResponse)
def email_status(
    _principal: AuthPrincipal = Depends(
        require_roles(UserRole.FINANCE_OPS, UserRole.OWNER_DIRECTOR, UserRole.COMPLIANCE)
    ),
    db: Session = Depends(get_db),
) -> EmailIntegrationStatusResponse:
    settings = get_settings()
    row = get_state(db)
    return EmailIntegrationStatusResponse(
        configured=getattr(settings, "email_worker_configured", settings.email_configured),
        status=row.status if row else "not_configured",
        folder_name=settings.email_imap_folder,
        last_uid=row.last_uid if row else 0,
        last_sync_at=row.last_sync_at if row else None,
        failure_code=row.failure_code if row else None,
    )


@router.post("/integrations/email/sync", response_model=EmailSyncResponse)
def email_sync(
    _principal: AuthPrincipal = Depends(
        require_roles(UserRole.FINANCE_OPS, UserRole.OWNER_DIRECTOR)
    ),
    db: Session = Depends(get_db),
) -> EmailSyncResponse:
    try:
        result = sync_mailbox(db)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return EmailSyncResponse(
        examined=result.examined,
        protected=result.protected,
        ready=result.ready,
        failed=result.failed,
        last_uid=result.last_uid,
    )
