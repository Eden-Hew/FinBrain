from datetime import UTC, datetime

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
    OutreachEvidence,
    ProtectedTokenRegistry,
    TenantOutreachPolicy,
)
from app.schemas import (
    CustomerEndpointCreateRequest,
    CustomerEndpointResponse,
    CustomerIdentityClaimDecisionRequest,
    CustomerIdentityClaimResponse,
    OutreachActionResponse,
    OutreachCreateRequest,
    OutreachGenerateRequest,
    OutreachStatusResponse,
    OutreachUpdateRequest,
    TenantOutreachPolicyResponse,
    TenantOutreachPolicyUpdate,
    UserRole,
)
from app.security.detokenize import detokenize_response_with_trace, hash_query
from app.services.outreach import (
    create_action,
    endpoint_mask,
    generate_action,
    get_action,
    register_email_endpoint,
    resolve_identity_claim,
    revoke_endpoint,
    transition_action,
    update_draft,
    verify_endpoint,
)
from app.services.workflow_audit import write_workflow_event

router = APIRouter(tags=["outreach"])
_MANAGE = (UserRole.FINANCE_OPS, UserRole.OWNER_DIRECTOR)


def _policy_response(row: TenantOutreachPolicy) -> TenantOutreachPolicyResponse:
    return TenantOutreachPolicyResponse.model_validate(row, from_attributes=True)


@router.get("/outreach-policy", response_model=TenantOutreachPolicyResponse)
def get_outreach_policy(
    principal: AuthPrincipal = Depends(require_roles(
        UserRole.FINANCE_OPS, UserRole.OWNER_DIRECTOR, UserRole.COMPLIANCE
    )),
    db: Session = Depends(get_db),
):
    tenant_id = str(principal.tenant_id)
    row = db.get(TenantOutreachPolicy, tenant_id)
    if row is None:
        return TenantOutreachPolicyResponse(
            telegram_reminders_enabled=False,
            grace_days=1,
            repeat_interval_days=7,
            max_reminders=3,
            require_approval=True,
            policy_version=1,
            updated_at=datetime.now(UTC),
        )
    return _policy_response(row)


@router.put("/outreach-policy", response_model=TenantOutreachPolicyResponse)
def update_outreach_policy(
    payload: TenantOutreachPolicyUpdate,
    principal: AuthPrincipal = Depends(require_roles(UserRole.OWNER_DIRECTOR)),
    db: Session = Depends(get_db),
):
    tenant_id = str(principal.tenant_id)
    row = db.get(TenantOutreachPolicy, tenant_id)
    if row is None:
        row = TenantOutreachPolicy(tenant_id=tenant_id)
        db.add(row)
    previous_enabled = row.telegram_reminders_enabled
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    row.policy_version += 1
    row.updated_by_user_id = str(principal.user_id)
    write_workflow_event(
        db,
        event_type="tenant_outreach_policy_updated",
        actor_role=principal.role.value,
        actor_ref=principal.actor_ref,
        resource_type="tenant_outreach_policy",
        resource_id=tenant_id,
        tenant_id=tenant_id,
        event_payload={
            "telegram_reminders_enabled": row.telegram_reminders_enabled,
            "previous_enabled": previous_enabled,
            "require_approval": row.require_approval,
            "policy_version": row.policy_version,
        },
    )
    db.commit()
    return _policy_response(row)


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


def _action_response(
    db: Session,
    response: OutreachActionResponse,
    principal: AuthPrincipal,
    *,
    generation_mode: str | None = None,
) -> OutreachActionResponse:
    endpoint = db.get(CustomerEndpoint, response.customer_endpoint_id)
    recipient = endpoint_mask(db, endpoint) if endpoint is not None else None
    if endpoint is not None and principal.role is UserRole.OWNER_DIRECTOR:
        endpoint_trace = detokenize_response_with_trace(
            db,
            endpoint.endpoint_token,
            principal.role.value,
            hash_query(f"outreach-recipient:{response.id}"),
            actor_ref=principal.actor_ref,
            turn_ref=f"outreach:{response.id}",
        )
        if endpoint_trace.restored_tokens == 1 and endpoint_trace.withheld_tokens == 0:
            recipient = endpoint_trace.text
    content_trace = detokenize_response_with_trace(
        db,
        f"{response.protected_subject}\n\u0000\n{response.protected_body}",
        principal.role.value,
        hash_query(f"outreach-preview:{response.id}"),
        actor_ref=principal.actor_ref,
        turn_ref=f"outreach:{response.id}",
    )
    subject, body = content_trace.text.split("\n\u0000\n", 1)
    evidence_ids = list(
        db.scalars(
            select(OutreachEvidence.tokenized_content_id).where(
                OutreachEvidence.tenant_id == str(principal.tenant_id),
                OutreachEvidence.outreach_action_id == response.id,
            )
        ).all()
    )
    return response.model_copy(
        update={
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "evidence_content_ids": evidence_ids,
            "generation_mode": generation_mode,
        }
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
        response = create_action(
            db, tenant_id=str(principal.tenant_id), customer_id=customer_id,
            endpoint_id=payload.customer_endpoint_id, subject=payload.subject,
            body=payload.body, idempotency_key=payload.idempotency_key,
            evidence_ids=payload.evidence_content_ids,
            created_by_user_id=str(principal.user_id), actor_role=principal.role.value,
            actor_ref=principal.actor_ref,
        )
        return _action_response(db, response, principal)
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
    return [_action_response(db, OutreachActionResponse.model_validate({
        "id": row.id, "customer_id": row.customer_id,
        "customer_endpoint_id": row.customer_endpoint_id, "channel": row.channel,
        "protected_subject": row.protected_subject, "protected_body": row.protected_body,
        "status": row.status, "idempotency_key": row.idempotency_key,
        "attempt_count": row.attempt_count, "failure_code": row.failure_code,
        "created_at": row.created_at, "approved_at": row.approved_at,
        "sent_at": row.sent_at, "replied_at": row.replied_at,
    }), principal) for row in db.scalars(select(OutreachAction).where(
        OutreachAction.tenant_id == str(principal.tenant_id)
    ).order_by(OutreachAction.created_at.desc())).all()]


@router.post(
    "/customers/{customer_id}/outreach/generate",
    response_model=OutreachActionResponse,
)
def generate_outreach(
    customer_id: int,
    payload: OutreachGenerateRequest,
    principal: AuthPrincipal = Depends(require_roles(*_MANAGE)),
    db: Session = Depends(get_db),
):
    _enabled()
    try:
        response, mode = generate_action(
            db,
            tenant_id=str(principal.tenant_id),
            customer_id=customer_id,
            endpoint_id=payload.customer_endpoint_id,
            turn_id=payload.turn_id,
            instruction=payload.instruction,
            idempotency_key=payload.idempotency_key,
            created_by_user_id=str(principal.user_id),
            actor_role=principal.role.value,
            actor_ref=principal.actor_ref,
        )
        return _action_response(db, response, principal, generation_mode=mode)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/outreach/{action_id}", response_model=OutreachActionResponse)
def get_outreach(
    action_id: str,
    principal: AuthPrincipal = Depends(require_roles(*_MANAGE)),
    db: Session = Depends(get_db),
):
    _enabled()
    try:
        response = get_action(db, action_id, tenant_id=str(principal.tenant_id))
    except LookupError as error:
        raise HTTPException(status_code=404, detail="outreach_action_not_found") from error
    return _action_response(db, response, principal)


@router.get("/outreach/{action_id}/status", response_model=OutreachStatusResponse)
def get_outreach_status(
    action_id: str,
    principal: AuthPrincipal = Depends(require_roles(*_MANAGE)),
    db: Session = Depends(get_db),
):
    _enabled()
    row = db.get(OutreachAction, action_id)
    if row is None or row.tenant_id != str(principal.tenant_id):
        raise HTTPException(status_code=404, detail="outreach_action_not_found")
    return OutreachStatusResponse(
        id=row.id,
        status=row.status,
        attempt_count=row.attempt_count,
        failure_code=row.failure_code,
        sent_at=row.sent_at,
        replied_at=row.replied_at,
    )


@router.patch("/outreach/{action_id}", response_model=OutreachActionResponse)
def edit_outreach(
    action_id: str,
    payload: OutreachUpdateRequest,
    principal: AuthPrincipal = Depends(require_roles(*_MANAGE)),
    db: Session = Depends(get_db),
):
    _enabled()
    try:
        response = update_draft(
            db,
            action_id,
            tenant_id=str(principal.tenant_id),
            subject=payload.subject,
            body=payload.body,
            actor_role=principal.role.value,
            actor_ref=principal.actor_ref,
        )
        return _action_response(db, response, principal)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/outreach/{action_id}/{operation}", response_model=OutreachActionResponse)
def decide_outreach(
    action_id: str, operation: str,
    principal: AuthPrincipal = Depends(require_roles(*_MANAGE)),
    db: Session = Depends(get_db),
):
    _enabled()
    try:
        response = transition_action(
            db, action_id, operation, tenant_id=str(principal.tenant_id),
            role=principal.role, user_id=str(principal.user_id),
            actor_ref=principal.actor_ref,
        )
        return _action_response(db, response, principal)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
