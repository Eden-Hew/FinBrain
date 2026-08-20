from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.auth.principal import AuthPrincipal
from app.config import get_settings
from app.db import get_db
from app.models import Customer, CustomerIdentityClaim
from app.schemas import (
    CustomerBriefingResponse,
    CustomerDetailResponse,
    CustomerSummaryResponse,
    CustomerTimelineItemResponse,
)
from app.security.detokenize import detokenize_response_with_trace, hash_query
from app.services.customer_intelligence import customer_detail, list_customers

router = APIRouter(tags=["customers"])


def _require_customer_intelligence() -> None:
    if not get_settings().customer_intelligence_enabled:
        raise HTTPException(status_code=503, detail="customer_intelligence_disabled")


def _authorized_customer_summary(
    db: Session,
    principal: AuthPrincipal,
    summary: CustomerSummaryResponse,
) -> CustomerSummaryResponse:
    customer = db.get(Customer, summary.id)
    if (
        customer is None
        or customer.tenant_id != str(principal.tenant_id)
        or customer.profile_status != "confirmed"
        or customer.identity_review_status != "clear"
        or customer.primary_name_token is None
    ):
        return summary
    accepted = db.scalar(
        select(CustomerIdentityClaim.id).where(
            CustomerIdentityClaim.tenant_id == str(principal.tenant_id),
            CustomerIdentityClaim.customer_id == customer.id,
            CustomerIdentityClaim.identity_token == customer.primary_name_token,
            CustomerIdentityClaim.status == "accepted",
        )
    )
    if accepted is None:
        return summary
    trace = detokenize_response_with_trace(
        db,
        customer.primary_name_token,
        principal.role.value,
        hash_query(f"customer-name:{customer.id}"),
        actor_ref=principal.actor_ref,
        turn_ref=f"customer-name:{customer.id}",
    )
    if trace.restored_tokens != 1 or trace.withheld_tokens != 0:
        return summary
    return summary.model_copy(update={"name": trace.text})


def _authorized_customer_detail(
    db: Session,
    principal: AuthPrincipal,
    detail: CustomerDetailResponse,
) -> CustomerDetailResponse:
    summary = _authorized_customer_summary(db, principal, detail)
    return detail.model_copy(update={"name": summary.name})


@router.get("/customers", response_model=list[CustomerSummaryResponse])
def customers(principal: CurrentUser, db: Session = Depends(get_db)):
    _require_customer_intelligence()
    return [
        _authorized_customer_summary(db, principal, row)
        for row in list_customers(db, str(principal.tenant_id))
    ]


@router.get("/customers/{customer_id}", response_model=CustomerDetailResponse)
def customer(customer_id: int, principal: CurrentUser, db: Session = Depends(get_db)):
    _require_customer_intelligence()
    try:
        return _authorized_customer_detail(
            db,
            principal,
            customer_detail(db, str(principal.tenant_id), customer_id),
        )
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
    rows = list_customers(db, str(principal.tenant_id))[:5]
    return CustomerBriefingResponse(
        generated_at=datetime.now(UTC),
        customers=[_authorized_customer_summary(db, principal, row) for row in rows],
    )
