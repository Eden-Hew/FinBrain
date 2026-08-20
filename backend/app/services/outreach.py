import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import (
    Customer,
    CustomerEndpoint,
    CustomerRecordLink,
    OutreachAction,
    OutreachEvidence,
    ProtectedTokenRegistry,
    TokenizedContent,
)
from app.schemas import OutreachActionResponse, UserRole
from app.security.detokenize import TOKEN_PATTERN
from app.security.protection import protect_text
from app.security.tokenize import persist_vault_entries
from app.services.workflow_audit import write_workflow_event


def _response(db: Session, row: OutreachAction) -> OutreachActionResponse:
    return OutreachActionResponse.model_validate(
        {
            "id": row.id,
            "customer_id": row.customer_id,
            "customer_endpoint_id": row.customer_endpoint_id,
            "channel": row.channel,
            "protected_subject": row.protected_subject,
            "protected_body": row.protected_body,
            "status": row.status,
            "idempotency_key": row.idempotency_key,
            "attempt_count": row.attempt_count,
            "failure_code": row.failure_code,
            "created_at": row.created_at,
            "approved_at": row.approved_at,
            "sent_at": row.sent_at,
            "replied_at": row.replied_at,
        }
    )


def register_email_endpoint(
    db: Session, *, tenant_id: str, customer_id: int, value: str,
    actor_role: str = "system", actor_ref: str = "system",
) -> CustomerEndpoint:
    customer = db.get(Customer, customer_id)
    if customer is None or customer.tenant_id != tenant_id:
        raise LookupError("customer_not_found")
    source_id = f"customer-endpoint:{uuid.uuid4()}"
    protected, entries = protect_text(value.strip(), source_id, tenant_id, db)
    tokens = TOKEN_PATTERN.findall(protected)
    if len(tokens) != 1 or protected.strip() != tokens[0] or not tokens[0].startswith("EMAIL_"):
        raise ValueError("valid_email_endpoint_required")
    persist_vault_entries(db, entries)
    existing = db.scalar(
        select(CustomerEndpoint).where(
            CustomerEndpoint.tenant_id == tenant_id,
            CustomerEndpoint.customer_id == customer_id,
            CustomerEndpoint.channel == "email",
            CustomerEndpoint.endpoint_token == tokens[0],
        )
    )
    if existing:
        if existing.verification_status == "revoked":
            existing.verification_status = "observed"
            existing.verified_by_user_id = None
            existing.verified_at = None
            write_workflow_event(
                db, event_type="customer_endpoint_restored", actor_role=actor_role,
                actor_ref=actor_ref, resource_type="customer_endpoint",
                resource_id=str(existing.id), tenant_id=tenant_id,
                event_payload={"customer_id": customer_id, "channel": "email"},
            )
        db.commit()
        return existing
    row = CustomerEndpoint(
        tenant_id=tenant_id, customer_id=customer_id, channel="email",
        endpoint_token=tokens[0], verification_status="observed",
    )
    db.add(row)
    db.commit()
    return row


def revoke_endpoint(
    db: Session, endpoint_id: int, *, tenant_id: str,
    actor_role: str, actor_ref: str,
) -> CustomerEndpoint:
    row = db.get(CustomerEndpoint, endpoint_id)
    if row is None or row.tenant_id != tenant_id:
        raise LookupError("customer_endpoint_not_found")
    if row.verification_status == "revoked":
        return row
    previous_status = row.verification_status
    row.verification_status = "revoked"
    write_workflow_event(
        db, event_type="customer_endpoint_revoked", actor_role=actor_role,
        actor_ref=actor_ref, resource_type="customer_endpoint",
        resource_id=str(row.id), tenant_id=tenant_id,
        event_payload={
            "customer_id": row.customer_id,
            "channel": row.channel,
            "previous_status": previous_status,
            "status": "revoked",
        },
    )
    db.commit()
    return row


def verify_endpoint(
    db: Session, endpoint_id: int, *, tenant_id: str, reviewer_id: str
) -> CustomerEndpoint:
    row = db.get(CustomerEndpoint, endpoint_id)
    if row is None or row.tenant_id != tenant_id:
        raise LookupError("customer_endpoint_not_found")
    if row.verification_status == "revoked":
        raise ValueError("revoked_endpoint_cannot_be_verified")
    row.verification_status = "verified"
    row.verified_by_user_id = reviewer_id
    row.verified_at = datetime.now(UTC)
    db.commit()
    return row


def create_action(
    db: Session, *, tenant_id: str, customer_id: int, endpoint_id: int,
    subject: str, body: str, idempotency_key: str, evidence_ids: list[int],
    created_by_user_id: str, actor_role: str, actor_ref: str,
) -> OutreachActionResponse:
    existing = db.scalar(select(OutreachAction).where(
        OutreachAction.tenant_id == tenant_id,
        OutreachAction.idempotency_key == idempotency_key,
    ))
    if existing:
        return _response(db, existing)
    endpoint = db.get(CustomerEndpoint, endpoint_id)
    if endpoint is None or endpoint.tenant_id != tenant_id or endpoint.customer_id != customer_id:
        raise LookupError("customer_endpoint_not_found")
    action_id = str(uuid.uuid4())
    subject_protected, subject_entries = protect_text(
        subject, f"outreach-subject:{action_id}", tenant_id, db
    )
    body_protected, body_entries = protect_text(
        body, f"outreach-body:{action_id}", tenant_id, db
    )
    persist_vault_entries(db, [*subject_entries, *body_entries])
    evidence_rows = db.scalars(select(TokenizedContent).where(
        TokenizedContent.tenant_id == tenant_id,
        TokenizedContent.id.in_(evidence_ids or [-1]),
        TokenizedContent.processing_status == "ready",
    )).all()
    if len(evidence_rows) != len(set(evidence_ids)):
        raise ValueError("invalid_outreach_evidence")
    linked_ids = set(db.scalars(select(CustomerRecordLink.tokenized_content_id).where(
        CustomerRecordLink.tenant_id == tenant_id,
        CustomerRecordLink.customer_id == customer_id,
        CustomerRecordLink.match_status == "verified",
        CustomerRecordLink.tokenized_content_id.in_(evidence_ids or [-1]),
    )).all())
    if set(evidence_ids) - linked_ids:
        raise ValueError("outreach_evidence_not_linked_to_customer")
    row = OutreachAction(
        id=action_id, tenant_id=tenant_id, customer_id=customer_id,
        customer_endpoint_id=endpoint_id, channel="email",
        protected_subject=subject_protected, protected_body=body_protected,
        status="draft", idempotency_key=idempotency_key,
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    db.flush()
    for content_id in dict.fromkeys(evidence_ids):
        db.add(OutreachEvidence(
            tenant_id=tenant_id, outreach_action_id=row.id,
            tokenized_content_id=content_id, purpose="supporting",
        ))
    write_workflow_event(
        db, event_type="outreach_drafted", actor_role=actor_role,
        actor_ref=actor_ref, resource_type="outreach_action", resource_id=row.id,
        tenant_id=tenant_id,
        event_payload={
            "customer_id": customer_id,
            "channel": "email",
            "evidence_count": len(evidence_ids),
        },
    )
    db.commit()
    return _response(db, row)


_TRANSITIONS = {
    "submit": ("draft", "pending_approval"),
    "approve": ("pending_approval", "approved"),
    "reject": ("pending_approval", "rejected"),
    "cancel": ("draft", "cancelled"),
}


def transition_action(
    db: Session, action_id: str, operation: str, *, tenant_id: str,
    role: UserRole, user_id: str, actor_ref: str,
) -> OutreachActionResponse:
    expected, target = _TRANSITIONS.get(operation, (None, None))
    if expected is None:
        raise ValueError("unsupported_outreach_transition")
    if operation in {"approve", "reject"} and role is not UserRole.OWNER_DIRECTOR:
        raise PermissionError("owner_director_required")
    row = db.get(OutreachAction, action_id)
    if row is None or row.tenant_id != tenant_id:
        raise LookupError("outreach_action_not_found")
    if operation in {"submit", "approve"}:
        endpoint = db.get(CustomerEndpoint, row.customer_endpoint_id)
        if endpoint is None or endpoint.verification_status != "verified":
            raise ValueError("verified_email_endpoint_required")
    values = {"status": target, "updated_at": datetime.now(UTC)}
    if operation == "approve":
        values.update({"approved_by_user_id": user_id, "approved_at": datetime.now(UTC)})
    changed = db.execute(update(OutreachAction).where(
        OutreachAction.id == action_id, OutreachAction.tenant_id == tenant_id,
        OutreachAction.status == expected,
    ).values(**values)).rowcount
    if changed != 1:
        db.rollback()
        raise ValueError(f"cannot_{operation}_outreach_from_{row.status}")
    write_workflow_event(
        db, event_type=f"outreach_{target}", actor_role=role.value,
        actor_ref=actor_ref, resource_type="outreach_action", resource_id=action_id,
        tenant_id=tenant_id, event_payload={"previous_status": expected, "status": target},
    )
    db.commit()
    return _response(db, db.get(OutreachAction, action_id))


def endpoint_mask(db: Session, row: CustomerEndpoint) -> str:
    registry = db.get(ProtectedTokenRegistry, row.endpoint_token)
    return registry.masked_value if registry else "*****@*******.***"
