import hashlib
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from telegram import Bot

from app.config import get_settings
from app.models import Customer, CustomerEndpoint, EInvoiceRecord, OutreachAction, TokenVaultEntry
from app.schemas import UserRole
from app.security.detokenize import detokenize_response_with_trace
from app.security.keyring import decrypt_vault_entry
from app.services.workflow_audit import write_workflow_event


async def dispatch_one(db: Session, bot: Bot | None = None) -> OutreachAction | None:
    settings = get_settings()
    if not settings.telegram_outbound_enabled:
        return None
    action = db.scalar(
        select(OutreachAction)
        .where(
            OutreachAction.channel == "telegram",
            OutreachAction.status == "approved",
            or_(
                OutreachAction.scheduled_for.is_(None),
                OutreachAction.scheduled_for <= datetime.now(UTC),
            ),
        )
        .order_by(OutreachAction.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if action is None:
        return None
    action.status = "sending"
    action.send_started_at = datetime.now(UTC)
    action.attempt_count += 1
    db.commit()

    endpoint = db.get(CustomerEndpoint, action.customer_endpoint_id)
    customer = db.get(Customer, action.customer_id)
    invoice = db.get(EInvoiceRecord, action.origin_invoice_id) if action.origin_invoice_id else None
    invalid = (
        endpoint is None
        or endpoint.tenant_id != action.tenant_id
        or endpoint.customer_id != action.customer_id
        or endpoint.channel != "telegram"
        or endpoint.verification_status != "verified"
        or endpoint.delivery_token is None
        or customer is None
        or customer.profile_status != "confirmed"
        or customer.identity_review_status != "clear"
        or (
            invoice is not None
            and (
                invoice.tenant_id != action.tenant_id
                or invoice.buyer_customer_id != action.customer_id
                or invoice.paid_at is not None
                or invoice.status != "validated"
            )
        )
    )
    if invalid:
        action.status = "cancelled"
        action.failure_code = "delivery_eligibility_changed"
        db.commit()
        return action
    vault = db.get(TokenVaultEntry, endpoint.delivery_token)
    if vault is None:
        action.status = "failed"
        action.failure_code = "telegram_delivery_destination_missing"
        db.commit()
        return action
    provider_accepted = False
    try:
        chat_id = int(decrypt_vault_entry(db, vault))
        query_ref = hashlib.sha256(f"telegram-outreach:{action.id}".encode()).hexdigest()
        body = detokenize_response_with_trace(
            db,
            action.protected_body,
            UserRole.OWNER_DIRECTOR.value,
            query_ref,
            actor_ref="telegram-outbound-worker",
            turn_ref=action.id,
        ).text
        telegram_bot = bot or Bot(token=settings.telegram_bot_token)
        sent = await telegram_bot.send_message(chat_id=chat_id, text=body)
        provider_accepted = True
        action.provider_message_ref_hash = hashlib.sha256(
            f"{chat_id}:{sent.message_id}".encode()
        ).hexdigest()
        action.status = "sent"
        action.sent_at = datetime.now(UTC)
        action.failure_code = None
        write_workflow_event(
            db,
            event_type="telegram_outreach_sent",
            actor_role="system_worker",
            actor_ref="telegram-outbound-worker",
            resource_type="outreach_action",
            resource_id=action.id,
            tenant_id=action.tenant_id,
            event_payload={"channel": "telegram", "attempt_count": action.attempt_count},
        )
        db.commit()
    except Exception:
        db.rollback()
        action = db.get(OutreachAction, action.id)
        if action is None:
            raise
        action.status = "delivery_unknown" if provider_accepted else "failed"
        action.failure_code = (
            "telegram_delivery_commit_unknown" if provider_accepted else "telegram_send_failed"
        )
        db.commit()
    return action
