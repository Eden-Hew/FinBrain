from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import (
    CanonicalIngestionRecord,
    IngestionRequest,
    IngestionResponse,
)
from app.services.ingestion import ingest_canonical_record

router = APIRouter(tags=["ingestion"])


@router.post("/ingestion", response_model=IngestionResponse)
def ingest(payload: IngestionRequest, db: Session = Depends(get_db)) -> IngestionResponse:
    """Proof-of-concept endpoint trusting the caller-selected role until Auth is added."""
    record = CanonicalIngestionRecord.model_validate(
        payload.model_dump(exclude={"role", "refresh"})
    )
    try:
        result = ingest_canonical_record(db, record, refresh=payload.refresh)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return IngestionResponse(
        **result.model_dump(),
        submitted_as=payload.role,
    )
