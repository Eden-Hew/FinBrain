from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    CustomerEndpoint,
    CustomerRecordLink,
    EmailIngestionReceipt,
    TokenizedContent,
)
from app.security.detokenize import TOKEN_PATTERN
from app.services.workflow_audit import write_workflow_event


def link_verified_sender(
    db: Session,
    *,
    receipt: EmailIngestionReceipt,
    protected_row: TokenizedContent,
) -> int | None:
    """Link a standalone email by exact protected sender token, never by name guessing."""
    sender_token = protected_row.safe_metadata.get("sender_email")
    if (
        not isinstance(sender_token, str)
        or not sender_token.startswith("EMAIL_")
        or TOKEN_PATTERN.fullmatch(sender_token) is None
    ):
        return None
    endpoints = db.scalars(
        select(CustomerEndpoint).where(
            CustomerEndpoint.tenant_id == protected_row.tenant_id,
            CustomerEndpoint.channel == "email",
            CustomerEndpoint.endpoint_token == sender_token,
            CustomerEndpoint.verification_status == "verified",
        )
    ).all()
    customer_ids = {row.customer_id for row in endpoints}
    if len(customer_ids) != 1:
        return None
    customer_id = customer_ids.pop()
    receipt.customer_id = customer_id
    existing = db.scalar(
        select(CustomerRecordLink).where(
            CustomerRecordLink.tenant_id == protected_row.tenant_id,
            CustomerRecordLink.customer_id == customer_id,
            CustomerRecordLink.tokenized_content_id == protected_row.id,
            CustomerRecordLink.match_basis == "exact_verified_email_endpoint",
        )
    )
    if existing is None:
        db.add(
            CustomerRecordLink(
                tenant_id=protected_row.tenant_id,
                customer_id=customer_id,
                tokenized_content_id=protected_row.id,
                alias_id=None,
                match_status="verified",
                confidence=1.0,
                match_basis="exact_verified_email_endpoint",
            )
        )
        write_workflow_event(
            db,
            event_type="email_sender_linked",
            actor_role="system_worker",
            actor_ref="email-worker",
            resource_type="tokenized_content",
            resource_id=str(protected_row.id),
            tenant_id=protected_row.tenant_id,
            event_payload={"customer_id": customer_id, "match": "verified_endpoint"},
        )
    db.commit()
    if get_settings().customer_attention_enabled:
        from app.services.customer_attention import recalculate_customer_attention

        recalculate_customer_attention(db, protected_row.tenant_id, customer_id)
    return customer_id
