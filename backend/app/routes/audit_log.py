from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuditLogEntry
from app.schemas import AuditEntryResponse, AuditResponse, UserRole
from app.services.audit import verify_audit_chain

router = APIRouter(tags=["audit"])


@router.get("/audit-log", response_model=AuditResponse)
def audit_log(role: UserRole = Query(...), db: Session = Depends(get_db)) -> AuditResponse:
    if role is not UserRole.COMPLIANCE:
        raise HTTPException(status_code=403, detail="Compliance role required")
    rows = db.scalars(select(AuditLogEntry).order_by(AuditLogEntry.id.desc()).limit(200)).all()
    return AuditResponse(
        entries=[
            AuditEntryResponse(
                id=row.id,
                role=row.user_role,
                token=row.token,
                authorized=row.authorized,
                query_hash=row.query_hash,
                ts=row.ts,
            )
            for row in rows
        ],
        chain_valid=verify_audit_chain(db),
    )
