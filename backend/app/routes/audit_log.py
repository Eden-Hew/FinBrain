from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.auth.principal import AuthPrincipal
from app.db import get_db
from app.models import AuditLogEntry, WorkflowAuditEntry
from app.schemas import (
    AuditEntryResponse,
    AuditResponse,
    UserRole,
    WorkflowAuditListResponse,
    WorkflowAuditResponse,
)
from app.services.audit import verify_audit_chain
from app.services.workflow_audit import verify_workflow_chain

router = APIRouter(tags=["audit"])


@router.get("/audit-log", response_model=AuditResponse)
def audit_log(
    principal: AuthPrincipal = Depends(require_roles(UserRole.COMPLIANCE)),
    db: Session = Depends(get_db),
) -> AuditResponse:
    tenant_id = str(principal.tenant_id)
    # A tenant's compliance view also includes system-level events (tenant_id is
    # null — e.g. vault key rotation) since those affect that tenant's data too.
    rows = db.scalars(
        select(AuditLogEntry)
        .where(or_(AuditLogEntry.tenant_id == tenant_id, AuditLogEntry.tenant_id.is_(None)))
        .order_by(AuditLogEntry.id.desc())
        .limit(200)
    ).all()
    return AuditResponse(
        entries=[
            AuditEntryResponse(
                id=row.id,
                role=row.user_role,
                token=row.token,
                authorized=row.authorized,
                query_hash=row.query_hash,
                actor_ref=row.actor_ref,
                previous_hash=row.prev_hash,
                entry_hash=row.event_hash,
                ts=row.ts,
            )
            for row in rows
        ],
        chain_valid=verify_audit_chain(db, tenant_id) and verify_audit_chain(db, None),
    )


@router.get("/workflow-audit", response_model=WorkflowAuditListResponse)
def workflow_audit(
    principal: AuthPrincipal = Depends(require_roles(UserRole.COMPLIANCE)),
    db: Session = Depends(get_db),
) -> WorkflowAuditListResponse:
    tenant_id = str(principal.tenant_id)
    rows = db.scalars(
        select(WorkflowAuditEntry)
        .where(
            or_(
                WorkflowAuditEntry.tenant_id == tenant_id,
                WorkflowAuditEntry.tenant_id.is_(None),
            )
        )
        .order_by(WorkflowAuditEntry.id.desc())
        .limit(200)
    ).all()
    return WorkflowAuditListResponse(
        entries=[
            WorkflowAuditResponse(
                id=row.id,
                event_type=row.event_type,
                actor_role=row.actor_role,
                actor_ref=row.actor_ref,
                resource_type=row.resource_type,
                resource_id=row.resource_id,
                event_payload=row.event_payload,
                previous_hash=row.prev_hash,
                entry_hash=row.event_hash,
                created_at=row.created_at,
            )
            for row in rows
        ],
        chain_valid=verify_workflow_chain(db, tenant_id) and verify_workflow_chain(db, None),
    )
