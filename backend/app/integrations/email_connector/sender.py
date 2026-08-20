import hashlib
import hmac
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import make_msgid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import CustomerEndpoint, OutreachAction, TokenVaultEntry
from app.schemas import UserRole
from app.security.detokenize import detokenize_response_with_trace, hash_query
from app.security.keyring import decrypt_vault_entry
from app.services.workflow_audit import write_workflow_event


def message_reference_hash(value: str) -> str:
    return hmac.new(
        get_settings().token_identity_secret.encode(),
        f"email-thread:{value.strip().casefold()}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _set_result(db: Session, row: OutreachAction, status: str, failure: str | None) -> None:
    row.status = status
    row.failure_code = failure
    row.updated_at = datetime.now(UTC)
    if status == "sent":
        row.sent_at = datetime.now(UTC)
    write_workflow_event(
        db,
        event_type=f"outreach_{status}",
        actor_role="system_worker",
        actor_ref="email-outbound-worker",
        resource_type="outreach_action",
        resource_id=row.id,
        tenant_id=row.tenant_id,
        event_payload={"status": status, "attempt_count": row.attempt_count},
    )
    db.commit()


def recover_stale_sends(db: Session) -> int:
    cutoff = datetime.now(UTC) - timedelta(seconds=get_settings().email_sending_stale_seconds)
    rows = db.scalars(
        select(OutreachAction).where(
            OutreachAction.status == "sending",
            OutreachAction.send_started_at < cutoff,
        )
    ).all()
    for row in rows:
        _set_result(db, row, "delivery_unknown", "worker_interrupted")
    return len(rows)


def _claim(db: Session) -> tuple[OutreachAction, str] | None:
    statement = (
        select(OutreachAction)
        .where(OutreachAction.status == "approved", OutreachAction.channel == "email")
        .order_by(OutreachAction.created_at)
        .limit(1)
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True)
    row = db.scalar(statement)
    if row is None:
        return None
    message_id = make_msgid(domain="finbrain.local")
    changed = db.execute(
        update(OutreachAction)
        .where(OutreachAction.id == row.id, OutreachAction.status == "approved")
        .values(
            status="sending",
            send_started_at=datetime.now(UTC),
            provider_message_ref_hash=message_reference_hash(message_id),
            attempt_count=OutreachAction.attempt_count + 1,
            updated_at=datetime.now(UTC),
        )
    ).rowcount
    if changed != 1:
        db.rollback()
        return None
    db.commit()
    return db.get(OutreachAction, row.id), message_id


def dispatch_one(db: Session) -> OutreachAction | None:
    claimed = _claim(db)
    if claimed is None:
        return None
    row, message_id = claimed
    settings = get_settings()
    endpoint = db.get(CustomerEndpoint, row.customer_endpoint_id)
    entry = db.get(TokenVaultEntry, endpoint.endpoint_token) if endpoint else None
    if endpoint is None or endpoint.verification_status != "verified" or entry is None:
        _set_result(db, row, "failed", "verified_endpoint_unavailable")
        return row
    try:
        recipient = decrypt_vault_entry(db, entry)
        query_ref = hash_query(f"outreach:{row.id}")
        subject = detokenize_response_with_trace(
            db, row.protected_subject, UserRole.OWNER_DIRECTOR.value, query_ref,
            actor_ref="email-outbound-worker", turn_ref=row.id,
        ).text
        body = detokenize_response_with_trace(
            db, row.protected_body, UserRole.OWNER_DIRECTOR.value, query_ref,
            actor_ref="email-outbound-worker", turn_ref=row.id,
        ).text
        username = settings.email_smtp_username or settings.email_imap_username
        password = settings.email_smtp_password or settings.email_imap_password
        sender = settings.email_smtp_from_address or username
        message = EmailMessage()
        message["From"] = sender
        message["To"] = recipient
        message["Subject"] = subject
        message["Message-ID"] = message_id
        message.set_content(body)
        with smtplib.SMTP(
            settings.email_smtp_host,
            settings.email_smtp_port,
            timeout=settings.email_send_timeout_seconds,
        ) as smtp:
            if settings.email_smtp_use_starttls:
                smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(message)
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError):
        _set_result(db, row, "failed", "smtp_rejected")
    except Exception:
        _set_result(db, row, "delivery_unknown", "smtp_delivery_uncertain")
    else:
        _set_result(db, row, "sent", None)
    return row


def dispatch_pending(db: Session) -> int:
    if not get_settings().email_smtp_configured:
        return 0
    count = 0
    for _ in range(get_settings().email_outbound_batch_size):
        if dispatch_one(db) is None:
            break
        count += 1
    return count
