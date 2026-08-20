from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.auth.principal import AuthPrincipal
from app.config import get_settings
from app.db import get_db
from app.models import (
    CustomerEndpoint,
    CustomerIdentityClaim,
    OutreachAction,
    ProtectedTokenRegistry,
)
from app.schemas import (
    CustomerEndpointCreateRequest,
    CustomerEndpointResponse,
    CustomerIdentityClaimDecisionRequest,
    CustomerIdentityClaimResponse,
    OutreachActionResponse,
    OutreachCreateRequest,
    UserRole,
)
from app.security.detokenize import detokenize_response_with_trace, hash_query
from app.services.outreach import (
    create_action,
    endpoint_mask,
    register_email_endpoint,
    resolve_identity_claim,
    revoke_endpoint,
    transition_action,
    verify_endpoint,
)

router = APIRouter(tags=["outreach"])
_MANAGE = (UserRole.FINANCE_OPS, UserRole.OWNER_DIRECTOR)


def _enabled() -> None:
    if not get_settings().customer_intelligence_enabled:
        raise HTTPException(status_code=503, detail="customer_intelligence_disabled")


def _endpoint_response(
    db: Session, row: CustomerEndpoint, principal: AuthPrincipal
) -> CustomerEndpointResponse:
    authorized_value = None
    if principal.role is UserRole.OWNER_DIRECTOR:
        trace = detokenize_response_with_trace(
            db,
            row.endpoint_token,
            principal.role.value,
            hash_query(f"customer-endpoint:{row.customer_id}:{row.id}"),
            actor_ref=principal.actor_ref,
            turn_ref=f"customer-endpoint:{row.id}",
        )
        if trace.restored_tokens == 1 and trace.withheld_tokens == 0:
            authorized_value = trace.text
    return CustomerEndpointResponse(
        id=row.id, customer_id=row.customer_id, channel=row.channel,
        masked_value=endpoint_mask(db, row), authorized_value=authorized_value,
        verification_status=row.verification_status,
        origin=row.origin,
        created_at=row.created_at,
    )


def _identity_claim_response(
    db: Session, row: CustomerIdentityClaim, principal: AuthPrincipal
) -> CustomerIdentityClaimResponse:
    registry = db.get(ProtectedTokenRegistry, row.identity_token)
    authorized_value = None
    if principal.role is UserRole.OWNER_DIRECTOR:
        trace = detokenize_response_with_trace(
            db,
            row.identity_token,
            principal.role.value,
            hash_query(f"customer-identity-claim:{row.id}"),
            actor_ref=principal.actor_ref,
            turn_ref=f"customer-identity-claim:{row.id}",
        )
        if trace.restored_tokens == 1 and trace.withheld_tokens == 0:
            authorized_value = trace.text
    return CustomerIdentityClaimResponse(
        id=row.id,
        customer_id=row.customer_id,
        endpoint_id=row.endpoint_id,
        masked_value=registry.masked_value if registry else "Protected identity",
        authorized_value=authorized_value,
        claim_basis=row.claim_basis,
        confidence=row.confidence,
        status=row.status,
        occurrence_count=row.occurrence_count,
        evidence_content_id=row.evidence_content_id,
        last_seen_at=row.last_seen_at,
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
            value=payload.value, actor_role=principal.role.value,
            actor_ref=principal.actor_ref,
        ), principal)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/customers/{customer_id}/endpoints",
    response_model=list[CustomerEndpointResponse],
)
def list_endpoints(
    customer_id: int,
    principal: AuthPrincipal = Depends(require_roles(*_MANAGE)),
    db: Session = Depends(get_db),
):
    _enabled()
    rows = db.scalars(select(CustomerEndpoint).where(
        CustomerEndpoint.tenant_id == str(principal.tenant_id),
        CustomerEndpoint.customer_id == customer_id,
    ).order_by(CustomerEndpoint.created_at.desc())).all()
    return [_endpoint_response(db, row, principal) for row in rows]


@router.get(
    "/customers/{customer_id}/identity-claims",
    response_model=list[CustomerIdentityClaimResponse],
)
def list_identity_claims(
    customer_id: int,
    principal: AuthPrincipal = Depends(require_roles(*_MANAGE, UserRole.COMPLIANCE)),
    db: Session = Depends(get_db),
):
    _enabled()
    rows = db.scalars(
        select(CustomerIdentityClaim).where(
            CustomerIdentityClaim.tenant_id == str(principal.tenant_id),
            CustomerIdentityClaim.customer_id == customer_id,
        ).order_by(CustomerIdentityClaim.last_seen_at.desc())
    ).all()
    return [_identity_claim_response(db, row, principal) for row in rows]


@router.post(
    "/customer-identity-claims/{claim_id}/resolve",
    response_model=CustomerIdentityClaimResponse,
)
def decide_identity_claim(
    claim_id: int,
    payload: CustomerIdentityClaimDecisionRequest,
    principal: AuthPrincipal = Depends(require_roles(UserRole.OWNER_DIRECTOR)),
    db: Session = Depends(get_db),
):
    _enabled()
    try:
        row = resolve_identity_claim(
            db,
            claim_id,
            tenant_id=str(principal.tenant_id),
            decision=payload.decision,
            reviewer_id=str(principal.user_id),
            actor_ref=principal.actor_ref,
        )
        return _identity_claim_response(db, row, principal)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


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
        ), principal)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/customer-endpoints/{endpoint_id}/revoke",
    response_model=CustomerEndpointResponse,
)
def revoke_customer_endpoint(
    endpoint_id: int,
    principal: AuthPrincipal = Depends(require_roles(UserRole.OWNER_DIRECTOR)),
    db: Session = Depends(get_db),
):
    _enabled()
    try:
        return _endpoint_response(db, revoke_endpoint(
            db, endpoint_id, tenant_id=str(principal.tenant_id),
            actor_role=principal.role.value, actor_ref=principal.actor_ref,
        ), principal)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


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
