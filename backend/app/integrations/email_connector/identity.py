import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Customer,
    CustomerEndpoint,
    CustomerIdentityClaim,
    CustomerRecordLink,
    EmailIngestionReceipt,
    TokenizedContent,
)
from app.security.detokenize import TOKEN_PATTERN
from app.services.workflow_audit import write_workflow_event

IDENTITY_TOKEN_PATTERN = re.compile(r"(?:PERSON|ORG)_[0-9a-f]{10}")
SELF_IDENTIFICATION_PATTERN = re.compile(
    r"\b(?:i\s+am|i['’]m|my\s+name\s+is|this\s+is)\s+"
    r"(?P<token>(?:PERSON|ORG)_[0-9a-f]{10})\b",
    re.IGNORECASE,
)


def _sender_token(row: TokenizedContent) -> str | None:
    value = row.safe_metadata.get("sender_email")
    if (
        isinstance(value, str)
        and value.startswith("EMAIL_")
        and TOKEN_PATTERN.fullmatch(value) is not None
    ):
        return value
    return None


def _claims(row: TokenizedContent, sender_token: str) -> list[tuple[str, str, float]]:
    claims: list[tuple[str, str, float]] = []
    from_line = next(
        (line for line in row.content_text.splitlines() if line.casefold().startswith("from:")),
        "",
    )
    if sender_token in from_line:
        display_tokens = IDENTITY_TOKEN_PATTERN.findall(from_line.split(sender_token, 1)[0])
        if len(set(display_tokens)) == 1:
            claims.append((display_tokens[0], "display_name", 0.8))
    for match in SELF_IDENTIFICATION_PATTERN.finditer(row.content_text):
        claims.append((match.group("token"), "self_identification", 0.95))
    structured = row.structured_summary or {}
    model_token = structured.get("sender_identity_token")
    model_basis = structured.get("sender_identity_basis")
    model_confidence = structured.get("sender_identity_confidence")
    if (
        isinstance(model_token, str)
        and model_token in set(IDENTITY_TOKEN_PATTERN.findall(row.content_text))
        and model_basis in {"display_name", "self_identification"}
        and isinstance(model_confidence, (float, int))
        and 0 <= float(model_confidence) <= 1
    ):
        claims.append((model_token, model_basis, float(model_confidence)))
    strongest: dict[tuple[str, str], float] = {}
    for token, basis, confidence in claims:
        key = (token, basis)
        strongest[key] = max(strongest.get(key, 0), confidence)
    return [(token, basis, confidence) for (token, basis), confidence in strongest.items()]


def _create_provisional_customer(
    db: Session, *, tenant_id: str, sender_token: str
) -> tuple[Customer, CustomerEndpoint]:
    suffix = sender_token.rsplit("_", 1)[-1].upper()
    customer = Customer(
        tenant_id=tenant_id,
        canonical_name=f"Email contact · {suffix[:6]}",
        normalized_name=f"EMAILCONTACT{suffix}",
        profile_status="provisional",
        identity_review_status="clear",
        profile_origin="email",
    )
    db.add(customer)
    db.flush()
    endpoint = CustomerEndpoint(
        tenant_id=tenant_id,
        customer_id=customer.id,
        channel="email",
        endpoint_token=sender_token,
        verification_status="observed",
        origin="inbound_email",
    )
    db.add(endpoint)
    db.flush()
    write_workflow_event(
        db,
        event_type="provisional_email_customer_created",
        actor_role="system_worker",
        actor_ref="email-worker",
        resource_type="customer",
        resource_id=str(customer.id),
        tenant_id=tenant_id,
        event_payload={"endpoint_id": endpoint.id, "profile_status": "provisional"},
    )
    return customer, endpoint


def _record_claims(
    db: Session,
    *,
    customer: Customer,
    endpoint: CustomerEndpoint,
    protected_row: TokenizedContent,
) -> None:
    candidates = _claims(protected_row, endpoint.endpoint_token)
    if not candidates:
        return
    now = datetime.now(UTC)
    if customer.primary_name_token is None:
        preferred = sorted(
            candidates,
            key=lambda value: (value[1] == "self_identification", value[2]),
            reverse=True,
        )[0]
        customer.primary_name_token = preferred[0]
    conflict = any(token != customer.primary_name_token for token, _basis, _c in candidates)
    if conflict:
        customer.identity_review_status = "review_required"
    for token, basis, confidence in candidates:
        existing = db.scalar(
            select(CustomerIdentityClaim).where(
                CustomerIdentityClaim.tenant_id == customer.tenant_id,
                CustomerIdentityClaim.customer_id == customer.id,
                CustomerIdentityClaim.endpoint_id == endpoint.id,
                CustomerIdentityClaim.identity_token == token,
                CustomerIdentityClaim.claim_basis == basis,
            )
        )
        claim_status = "conflicting" if token != customer.primary_name_token else "observed"
        if existing is None:
            db.add(
                CustomerIdentityClaim(
                    tenant_id=customer.tenant_id,
                    customer_id=customer.id,
                    endpoint_id=endpoint.id,
                    identity_token=token,
                    claim_basis=basis,
                    confidence=confidence,
                    evidence_content_id=protected_row.id,
                    status=claim_status,
                )
            )
        else:
            existing.confidence = max(existing.confidence, confidence)
            existing.evidence_content_id = protected_row.id
            existing.last_seen_at = now
            existing.occurrence_count += 1
            if existing.status not in {"accepted", "rejected"}:
                existing.status = claim_status
    if conflict:
        write_workflow_event(
            db,
            event_type="customer_identity_review_required",
            actor_role="system_worker",
            actor_ref="email-worker",
            resource_type="customer",
            resource_id=str(customer.id),
            tenant_id=customer.tenant_id,
            event_payload={"endpoint_id": endpoint.id, "evidence_content_id": protected_row.id},
        )


def route_email_sender(
    db: Session,
    *,
    receipt: EmailIngestionReceipt,
    protected_row: TokenizedContent,
) -> int | None:
    """Resolve an inbound sender endpoint and create a provisional profile when unknown."""
    sender_token = _sender_token(protected_row)
    if sender_token is None:
        return None
    endpoint = db.scalar(
        select(CustomerEndpoint).where(
            CustomerEndpoint.tenant_id == protected_row.tenant_id,
            CustomerEndpoint.channel == "email",
            CustomerEndpoint.endpoint_token == sender_token,
        )
    )
    if endpoint is not None and (
        endpoint.verification_status == "revoked"
        or (
            endpoint.verification_status != "verified"
            and endpoint.origin != "inbound_email"
        )
    ):
        return None
    created = False
    if endpoint is None:
        try:
            customer, endpoint = _create_provisional_customer(
                db, tenant_id=protected_row.tenant_id, sender_token=sender_token
            )
            created = True
        except IntegrityError:
            db.rollback()
            endpoint = db.scalar(
                select(CustomerEndpoint).where(
                    CustomerEndpoint.tenant_id == protected_row.tenant_id,
                    CustomerEndpoint.channel == "email",
                    CustomerEndpoint.endpoint_token == sender_token,
                )
            )
            if endpoint is None or endpoint.verification_status == "revoked":
                return None
            customer = db.get(Customer, endpoint.customer_id)
    else:
        customer = db.get(Customer, endpoint.customer_id)
    if customer is None:
        return None
    if receipt.customer_id not in {None, customer.id}:
        return None
    receipt.customer_id = customer.id
    basis = (
        "exact_verified_email_endpoint"
        if endpoint.verification_status == "verified"
        else "exact_inbound_email_endpoint"
    )
    existing_link = db.scalar(
        select(CustomerRecordLink).where(
            CustomerRecordLink.tenant_id == protected_row.tenant_id,
            CustomerRecordLink.customer_id == customer.id,
            CustomerRecordLink.tokenized_content_id == protected_row.id,
            CustomerRecordLink.match_basis == basis,
        )
    )
    if existing_link is None:
        db.add(
            CustomerRecordLink(
                tenant_id=protected_row.tenant_id,
                customer_id=customer.id,
                tokenized_content_id=protected_row.id,
                alias_id=None,
                match_status="verified",
                confidence=1.0,
                match_basis=basis,
            )
        )
    _record_claims(db, customer=customer, endpoint=endpoint, protected_row=protected_row)
    write_workflow_event(
        db,
        event_type="email_sender_linked",
        actor_role="system_worker",
        actor_ref="email-worker",
        resource_type="tokenized_content",
        resource_id=str(protected_row.id),
        tenant_id=protected_row.tenant_id,
        event_payload={
            "customer_id": customer.id,
            "match": "inbound_endpoint",
            "profile_created": created,
        },
    )
    db.commit()
    if get_settings().customer_attention_enabled:
        from app.services.customer_attention import recalculate_customer_attention

        recalculate_customer_attention(db, protected_row.tenant_id, customer.id)
    return customer.id


def link_verified_sender(
    db: Session,
    *,
    receipt: EmailIngestionReceipt,
    protected_row: TokenizedContent,
) -> int | None:
    """Compatibility name for the exact endpoint router used by existing callers."""
    return route_email_sender(db, receipt=receipt, protected_row=protected_row)
