from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.auth.principal import AuthPrincipal
from app.db import get_db
from app.schemas import (
    CanonicalIngestionRecord,
    IngestionRequest,
    IngestionResponse,
    UserRole,
)
from app.services.ingestion import ingest_canonical_record

router = APIRouter(tags=["ingestion"])


@router.post("/ingestion", response_model=IngestionResponse)
def ingest(
    payload: IngestionRequest,
    principal: AuthPrincipal = Depends(
        require_roles(UserRole.FINANCE_OPS, UserRole.OWNER_DIRECTOR)
    ),
    db: Session = Depends(get_db),
) -> IngestionResponse:
    """Protected ingestion authorized by a verified Supabase principal."""
    record = CanonicalIngestionRecord.model_validate(
        payload.model_dump(exclude={"refresh"})
    )
    try:
        result = ingest_canonical_record(db, record, refresh=payload.refresh)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return IngestionResponse(
        **result.model_dump(),
        submitted_as=principal.role,
    )
