from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.config import get_settings
from app.db import get_db
from app.schemas import (
    CustomerBriefingResponse,
    CustomerDetailResponse,
    CustomerSummaryResponse,
    CustomerTimelineItemResponse,
)
from app.services.customer_intelligence import customer_detail, list_customers

router = APIRouter(tags=["customers"])


def _require_customer_intelligence() -> None:
    if not get_settings().customer_intelligence_enabled:
        raise HTTPException(status_code=503, detail="customer_intelligence_disabled")


@router.get("/customers", response_model=list[CustomerSummaryResponse])
def customers(principal: CurrentUser, db: Session = Depends(get_db)):
    _require_customer_intelligence()
    return list_customers(db, str(principal.tenant_id))


@router.get("/customers/{customer_id}", response_model=CustomerDetailResponse)
def customer(customer_id: int, principal: CurrentUser, db: Session = Depends(get_db)):
    _require_customer_intelligence()
    try:
        return customer_detail(db, str(principal.tenant_id), customer_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get(
    "/customers/{customer_id}/timeline",
    response_model=list[CustomerTimelineItemResponse],
)
def customer_timeline(customer_id: int, principal: CurrentUser, db: Session = Depends(get_db)):
    _require_customer_intelligence()
    try:
        return customer_detail(db, str(principal.tenant_id), customer_id).timeline
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/briefing", response_model=CustomerBriefingResponse)
def briefing(principal: CurrentUser, db: Session = Depends(get_db)):
    _require_customer_intelligence()
    return CustomerBriefingResponse(
        generated_at=datetime.now(UTC),
        customers=list_customers(db, str(principal.tenant_id))[:5],
    )
