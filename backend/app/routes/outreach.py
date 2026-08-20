from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.auth.principal import AuthPrincipal
from app.config import get_settings
from app.db import get_db
from app.models import CustomerEndpoint, OutreachAction
from app.schemas import (
    CustomerEndpointCreateRequest,
    CustomerEndpointResponse,
    OutreachActionResponse,
    OutreachCreateRequest,
    UserRole,
)
from app.services.outreach import (
    create_action,
    endpoint_mask,
    register_email_endpoint,
    transition_action,
    verify_endpoint,
)

router = APIRouter(tags=["outreach"])
_MANAGE = (UserRole.FINANCE_OPS, UserRole.OWNER_DIRECTOR)


def _enabled() -> None:
    if not get_settings().customer_intelligence_enabled:
        raise HTTPException(status_code=503, detail="customer_intelligence_disabled")


def _endpoint_response(db: Session, row: CustomerEndpoint) -> CustomerEndpointResponse:
    return CustomerEndpointResponse(
        id=row.id, customer_id=row.customer_id, channel=row.channel,
        masked_value=endpoint_mask(db, row), verification_status=row.verification_status,
        created_at=row.created_at,
    )


@router.post("/customers/{customer_id}/endpoints", response_model=CustomerEndpointResponse)
def create_endpoint(
    customer_id: int, payload: CustomerEndpointCreateRequest,
    principal: AuthPrincipal = Depends(require_roles(*_MANAGE)),
    db: Session = Depends(get_db),
):
    _enabled()
    try:
        return _endpoint_response(db, register_email_endpoint(
            db, tenant_id=str(principal.tenant_id), customer_id=customer_id,
            value=payload.value,
        ))
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/customer-endpoints/{endpoint_id}/verify", response_model=CustomerEndpointResponse)
def confirm_endpoint(
    endpoint_id: int,
    principal: AuthPrincipal = Depends(require_roles(UserRole.OWNER_DIRECTOR)),
    db: Session = Depends(get_db),
):
    _enabled()
    try:
        return _endpoint_response(db, verify_endpoint(
            db, endpoint_id, tenant_id=str(principal.tenant_id),
            reviewer_id=str(principal.user_id),
        ))
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/customers/{customer_id}/outreach", response_model=OutreachActionResponse)
def draft_outreach(
    customer_id: int, payload: OutreachCreateRequest,
    principal: AuthPrincipal = Depends(require_roles(*_MANAGE)),
    db: Session = Depends(get_db),
):
    _enabled()
    try:
        return create_action(
            db, tenant_id=str(principal.tenant_id), customer_id=customer_id,
            endpoint_id=payload.customer_endpoint_id, subject=payload.subject,
            body=payload.body, idempotency_key=payload.idempotency_key,
            evidence_ids=payload.evidence_content_ids,
            created_by_user_id=str(principal.user_id), actor_role=principal.role.value,
            actor_ref=principal.actor_ref,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/outreach", response_model=list[OutreachActionResponse])
def list_outreach(
    principal: AuthPrincipal = Depends(require_roles(
        UserRole.FINANCE_OPS, UserRole.OWNER_DIRECTOR, UserRole.COMPLIANCE
    )), db: Session = Depends(get_db),
):
    _enabled()
    return [OutreachActionResponse.model_validate({
        "id": row.id, "customer_id": row.customer_id,
        "customer_endpoint_id": row.customer_endpoint_id, "channel": row.channel,
        "protected_subject": row.protected_subject, "protected_body": row.protected_body,
        "status": row.status, "idempotency_key": row.idempotency_key,
        "attempt_count": row.attempt_count, "failure_code": row.failure_code,
        "created_at": row.created_at, "approved_at": row.approved_at,
        "sent_at": row.sent_at, "replied_at": row.replied_at,
    }) for row in db.scalars(select(OutreachAction).where(
        OutreachAction.tenant_id == str(principal.tenant_id)
    ).order_by(OutreachAction.created_at.desc())).all()]


@router.post("/outreach/{action_id}/{operation}", response_model=OutreachActionResponse)
def decide_outreach(
    action_id: str, operation: str,
    principal: AuthPrincipal = Depends(require_roles(*_MANAGE)),
    db: Session = Depends(get_db),
):
    _enabled()
    try:
        return transition_action(
            db, action_id, operation, tenant_id=str(principal.tenant_id),
            role=principal.role, user_id=str(principal.user_id),
            actor_ref=principal.actor_ref,
        )
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
