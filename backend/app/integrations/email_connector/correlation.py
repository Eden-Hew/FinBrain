from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.email_connector.identity import sender_token_for
from app.models import (
    CustomerEndpoint,
    CustomerRecordLink,
    EmailIngestionReceipt,
    EmailReplyCorrelation,
    OutreachAction,
    TokenizedContent,
)
from app.services.workflow_audit import write_workflow_event


def correlate_reply(
    db: Session,
    *,
    receipt: EmailIngestionReceipt,
    protected_row: TokenizedContent,
    reference_hashes: tuple[str, ...],
) -> OutreachAction | None:
    if not get_settings().email_reply_correlation_enabled or not reference_hashes:
        return None
    actions = db.scalars(
        select(OutreachAction).where(
            OutreachAction.tenant_id == protected_row.tenant_id,
            OutreachAction.provider_message_ref_hash.in_(reference_hashes),
            OutreachAction.status.in_(("sent", "delivery_unknown")),
        )
    ).all()
    if len(actions) != 1:
        if len(actions) > 1:
            receipt.correlation_status = "ambiguous"
            db.commit()
        return None
    action = actions[0]
    matched = next(
        value for value in reference_hashes if value == action.provider_message_ref_hash
    )
    endpoint = db.get(CustomerEndpoint, action.customer_endpoint_id)
    sender_token = sender_token_for(protected_row)
    if (
        endpoint is None
        or not isinstance(sender_token, str)
        or sender_token != endpoint.endpoint_token
    ):
        receipt.outreach_action_id = action.id
        receipt.in_reply_to_ref_hash = reference_hashes[0]
        receipt.correlation_status = "identity_conflict"
        existing = db.scalar(
            select(EmailReplyCorrelation).where(
                EmailReplyCorrelation.email_receipt_ref_hash == receipt.message_ref_hash,
                EmailReplyCorrelation.outreach_action_id == action.id,
            )
        )
        if existing is None:
            db.add(
                EmailReplyCorrelation(
                    tenant_id=action.tenant_id,
                    email_receipt_ref_hash=receipt.message_ref_hash,
                    outreach_action_id=action.id,
                    matched_reference_hash=matched,
                    customer_id=action.customer_id,
                    tokenized_content_id=protected_row.id,
                    status="identity_conflict",
                )
            )
        write_workflow_event(
            db,
            event_type="email_reply_identity_conflict",
            actor_role="system_worker",
            actor_ref="email-worker",
            resource_type="outreach_action",
            resource_id=action.id,
            tenant_id=action.tenant_id,
            event_payload={"tokenized_content_id": protected_row.id},
        )
        db.commit()
        return None
    receipt.customer_id = action.customer_id
    receipt.outreach_action_id = action.id
    receipt.in_reply_to_ref_hash = reference_hashes[0]
    receipt.correlation_status = "correlated"
    receipt.correlated_at = datetime.now(UTC)
    existing = db.scalar(
        select(EmailReplyCorrelation).where(
            EmailReplyCorrelation.email_receipt_ref_hash == receipt.message_ref_hash,
            EmailReplyCorrelation.outreach_action_id == action.id,
        )
    )
    if existing is None:
        db.add(
            EmailReplyCorrelation(
                tenant_id=action.tenant_id,
                email_receipt_ref_hash=receipt.message_ref_hash,
                outreach_action_id=action.id,
                matched_reference_hash=matched,
                customer_id=action.customer_id,
                tokenized_content_id=protected_row.id,
                status="correlated",
            )
        )
    link = db.scalar(
        select(CustomerRecordLink).where(
            CustomerRecordLink.tenant_id == action.tenant_id,
            CustomerRecordLink.customer_id == action.customer_id,
            CustomerRecordLink.tokenized_content_id == protected_row.id,
            CustomerRecordLink.match_basis == "exact_email_reply",
        )
    )
    if link is None:
        db.add(
            CustomerRecordLink(
                tenant_id=action.tenant_id,
                customer_id=action.customer_id,
                tokenized_content_id=protected_row.id,
                alias_id=None,
                match_status="verified",
                confidence=1.0,
                match_basis="exact_email_reply",
            )
        )
    action.status = "replied"
    action.replied_at = receipt.correlated_at
    write_workflow_event(
        db,
        event_type="email_reply_correlated",
        actor_role="system_worker",
        actor_ref="email-worker",
        resource_type="outreach_action",
        resource_id=action.id,
        tenant_id=action.tenant_id,
        event_payload={
            "customer_id": action.customer_id,
            "tokenized_content_id": protected_row.id,
        },
    )
    db.commit()
    if get_settings().customer_attention_enabled:
        from app.services.customer_attention import recalculate_customer_attention

        recalculate_customer_attention(db, action.tenant_id, action.customer_id)
    return action
