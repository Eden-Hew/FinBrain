from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, CustomerEndpoint, CustomerRecordLink, EInvoiceRecord
from app.services.workflow_audit import write_workflow_event


@dataclass(frozen=True, slots=True)
class EndpointEvidence:
    tenant_id: str
    name_token: str
    email_token: str
    phone_token: str
    telegram_endpoint_token: str
    telegram_delivery_token: str
    evidence_content_id: int


@dataclass(frozen=True, slots=True)
class EndpointResolutionResult:
    customer_id: int
    telegram_endpoint_id: int
    created: bool
    review_required: bool = False


def _endpoint(db: Session, tenant_id: str, channel: str, token: str) -> CustomerEndpoint | None:
    return db.scalar(
        select(CustomerEndpoint).where(
            CustomerEndpoint.tenant_id == tenant_id,
            CustomerEndpoint.channel == channel,
            CustomerEndpoint.endpoint_token == token,
        )
    )


def _add_endpoint(
    db: Session,
    *,
    tenant_id: str,
    customer_id: int,
    channel: str,
    token: str,
    verification_status: str,
    origin: str,
    delivery_token: str | None = None,
) -> CustomerEndpoint:
    existing = _endpoint(db, tenant_id, channel, token)
    if existing is not None:
        if existing.customer_id != customer_id:
            raise ValueError(f"{channel}_endpoint_already_owned")
        if existing.verification_status == "revoked":
            raise ValueError(f"{channel}_endpoint_revoked")
        if verification_status == "verified":
            existing.verification_status = "verified"
        if delivery_token is not None:
            existing.delivery_token = delivery_token
        return existing
    row = CustomerEndpoint(
        tenant_id=tenant_id,
        customer_id=customer_id,
        channel=channel,
        endpoint_token=token,
        delivery_token=delivery_token or (token if channel == "email" else None),
        verification_status=verification_status,
        origin=origin,
    )
    db.add(row)
    db.flush()
    return row


def resolve_customer_endpoint(
    db: Session, evidence: EndpointEvidence
) -> EndpointResolutionResult:
    """Resolve one protected Telegram identity bundle to exactly one tenant customer."""
    candidates = {
        row.customer_id
        for row in (
            _endpoint(db, evidence.tenant_id, "telegram", evidence.telegram_endpoint_token),
            _endpoint(db, evidence.tenant_id, "email", evidence.email_token),
            _endpoint(db, evidence.tenant_id, "phone", evidence.phone_token),
        )
        if row is not None and row.verification_status != "revoked"
    }
    if len(candidates) > 1:
        for customer_id in candidates:
            customer = db.get(Customer, customer_id)
            if customer is not None:
                customer.identity_review_status = "review_required"
        write_workflow_event(
            db,
            event_type="telegram_identity_review_required",
            actor_role="system_worker",
            actor_ref="telegram-onboarding-worker",
            resource_type="tokenized_content",
            resource_id=str(evidence.evidence_content_id),
            tenant_id=evidence.tenant_id,
            event_payload={"candidate_count": len(candidates)},
        )
        db.commit()
        raise ValueError("conflicting_customer_endpoints")

    created = not candidates
    if candidates:
        customer = db.get(Customer, next(iter(candidates)))
        if customer is None:
            raise LookupError("customer_not_found")
    else:
        suffix = evidence.email_token.rsplit("_", 1)[-1].upper()
        customer = Customer(
            tenant_id=evidence.tenant_id,
            canonical_name=f"Telegram contact - {suffix[:6]}",
            normalized_name=f"TELEGRAMCONTACT{suffix}",
            profile_status="provisional",
            identity_review_status="clear",
            profile_origin="telegram",
            primary_name_token=evidence.name_token,
        )
        db.add(customer)
        db.flush()

    if customer.primary_name_token is None:
        customer.primary_name_token = evidence.name_token
    telegram = _add_endpoint(
        db,
        tenant_id=evidence.tenant_id,
        customer_id=customer.id,
        channel="telegram",
        token=evidence.telegram_endpoint_token,
        delivery_token=evidence.telegram_delivery_token,
        verification_status="verified",
        origin="telegram_onboarding",
    )
    _add_endpoint(
        db,
        tenant_id=evidence.tenant_id,
        customer_id=customer.id,
        channel="email",
        token=evidence.email_token,
        verification_status="observed",
        origin="telegram_onboarding",
    )
    _add_endpoint(
        db,
        tenant_id=evidence.tenant_id,
        customer_id=customer.id,
        channel="phone",
        token=evidence.phone_token,
        verification_status="verified",
        origin="telegram_contact_share",
    )
    customer.profile_status = "confirmed"
    link = db.scalar(
        select(CustomerRecordLink).where(
            CustomerRecordLink.tenant_id == evidence.tenant_id,
            CustomerRecordLink.customer_id == customer.id,
            CustomerRecordLink.tokenized_content_id == evidence.evidence_content_id,
            CustomerRecordLink.match_basis == "telegram_onboarding_profile",
        )
    )
    if link is None:
        db.add(CustomerRecordLink(
            tenant_id=evidence.tenant_id,
            customer_id=customer.id,
            tokenized_content_id=evidence.evidence_content_id,
            match_status="verified",
            confidence=1.0,
            match_basis="telegram_onboarding_profile",
        ))
    for invoice in db.scalars(select(EInvoiceRecord).where(
        EInvoiceRecord.tenant_id == evidence.tenant_id,
        EInvoiceRecord.buyer_customer_id.is_(None),
        EInvoiceRecord.buyer_email_token == evidence.email_token,
    )).all():
        invoice.buyer_customer_id = customer.id
    write_workflow_event(
        db,
        event_type="telegram_customer_resolved",
        actor_role="system_worker",
        actor_ref="telegram-onboarding-worker",
        resource_type="customer",
        resource_id=str(customer.id),
        tenant_id=evidence.tenant_id,
        event_payload={"profile_created": created, "telegram_endpoint_id": telegram.id},
    )
    db.commit()
    return EndpointResolutionResult(
        customer_id=customer.id,
        telegram_endpoint_id=telegram.id,
        created=created,
    )
