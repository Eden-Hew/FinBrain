import imaplib
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.email_connector.adapter import (
    canonical_record,
    mailbox_reference,
    message_reference,
)
from app.integrations.email_connector.correlation import correlate_reply
from app.integrations.email_connector.extractor import extract_email, extract_reply_references
from app.integrations.email_connector.identity import route_email_sender
from app.integrations.email_connector.sender import message_reference_hash
from app.models import EmailIngestionReceipt, EmailSyncState, TokenizedContent, utcnow
from app.services.ingestion import ingest_canonical_record

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SyncResult:
    examined: int
    protected: int
    ready: int
    failed: int
    last_uid: int


def _state(db: Session) -> EmailSyncState:
    settings = get_settings()
    key = "imap-primary"
    row = db.get(EmailSyncState, key)
    if row is None:
        row = EmailSyncState(
            connector_key=key,
            mailbox_ref=mailbox_reference(settings.email_imap_username),
            folder_name=settings.email_imap_folder,
            last_uid=0,
            status="idle",
        )
        db.add(row)
        db.commit()
    return row


def get_state(db: Session) -> EmailSyncState | None:
    return db.get(EmailSyncState, "imap-primary")


def _connect():
    settings = get_settings()
    connection = (
        imaplib.IMAP4_SSL(settings.email_imap_host, settings.email_imap_port)
        if settings.email_imap_use_ssl
        else imaplib.IMAP4(settings.email_imap_host, settings.email_imap_port)
    )
    connection.login(settings.email_imap_username, settings.email_imap_password)
    return connection


def _unread_search_criteria(last_uid: int) -> tuple[str, ...]:
    """Select unread deliveries without rescanning messages behind the durable cursor."""
    if last_uid == 0:
        return ("UNSEEN",)
    return "UNSEEN", f"UID {last_uid + 1}:*"


def _new_uid_values(raw: bytes, *, last_uid: int, limit: int) -> list[int]:
    """Defend against servers returning the terminal UID for an empty n:* range."""
    return [uid for value in raw.split() if (uid := int(value)) > last_uid][:limit]


def _protected_row_for_receipt(
    db: Session, receipt: EmailIngestionReceipt
) -> TokenizedContent | None:
    if receipt.source_record_id is None:
        return None
    return db.scalar(
        select(TokenizedContent).where(
            TokenizedContent.source_record_id == receipt.source_record_id
        )
    )


def reconcile_receipt(
    db: Session,
    *,
    receipt: EmailIngestionReceipt,
    reference_hashes: tuple[str, ...] = (),
) -> int | None:
    """Idempotently finish customer routing and optional outbound correlation."""
    protected_row = _protected_row_for_receipt(db, receipt)
    if protected_row is None:
        return None
    # Sender routing also restores sender_email from the protected From header
    # for records ingested before sender metadata was persisted reliably.
    customer_id = route_email_sender(
        db,
        receipt=receipt,
        protected_row=protected_row,
    )
    stored_reference = receipt.in_reply_to_ref_hash
    effective_references = reference_hashes or (
        (stored_reference,) if stored_reference else ()
    )
    correlate_reply(
        db,
        receipt=receipt,
        protected_row=protected_row,
        reference_hashes=effective_references,
    )
    return customer_id


def reconcile_unassigned_receipts(db: Session, *, limit: int) -> int:
    """Retry the bounded post-ingestion backlog without re-ingesting messages."""
    receipts = db.scalars(
        select(EmailIngestionReceipt)
        .where(
            EmailIngestionReceipt.customer_id.is_(None),
            EmailIngestionReceipt.source_record_id.is_not(None),
            EmailIngestionReceipt.status.in_(("protected", "ready")),
        )
        .order_by(EmailIngestionReceipt.received_at.desc())
        .limit(limit)
    ).all()
    reconciled = 0
    for receipt in receipts:
        try:
            if reconcile_receipt(db, receipt=receipt) is not None:
                reconciled += 1
        except Exception as error:
            db.rollback()
            logger.warning(
                "email_receipt_reconciliation_failed receipt=%s error_type=%s",
                receipt.message_ref_hash[:12],
                type(error).__name__,
            )
    return reconciled


def sync_mailbox(db: Session) -> SyncResult:
    settings = get_settings()
    if not settings.email_configured:
        raise RuntimeError("Email connector is not configured")
    state = _state(db)
    state.status = "syncing"
    state.failure_code = None
    db.commit()
    reconcile_unassigned_receipts(
        db,
        limit=settings.email_max_messages_per_sync,
    )
    examined = protected = ready = failed = 0
    last_uid = state.last_uid
    connection = None
    try:
        connection = _connect()
        status, _ = connection.select(settings.email_imap_folder, readonly=True)
        if status != "OK":
            raise RuntimeError("mailbox_select_failed")
        status, data = connection.uid(
            "search", None, *_unread_search_criteria(state.last_uid)
        )
        if status != "OK":
            raise RuntimeError("mailbox_search_failed")
        uid_values = _new_uid_values(
            data[0] or b"",
            last_uid=state.last_uid,
            limit=settings.email_max_messages_per_sync,
        )
        for uid in uid_values:
            examined += 1
            try:
                status, fetched = connection.uid("fetch", str(uid), "(RFC822)")
                if status != "OK" or not fetched or not isinstance(fetched[0], tuple):
                    raise RuntimeError("message_fetch_failed")
                raw_message = fetched[0][1]
                (
                    extracted,
                    occurred_at,
                    message_id,
                    attachment_count,
                    sender_address,
                ) = extract_email(raw_message)
                reply_hashes = tuple(
                    message_reference_hash(value)
                    for value in extract_reply_references(raw_message)
                )
                receipt_key = message_reference(
                    connector_key=state.connector_key,
                    folder=state.folder_name,
                    uid=uid,
                    message_id=message_id,
                )
                receipt = db.get(EmailIngestionReceipt, receipt_key)
                if receipt is not None:
                    reconcile_receipt(
                        db,
                        receipt=receipt,
                        reference_hashes=reply_hashes,
                    )
                    last_uid = uid
                    continue
                receipt = EmailIngestionReceipt(
                    message_ref_hash=receipt_key,
                    status="received",
                    in_reply_to_ref_hash=reply_hashes[0] if reply_hashes else None,
                )
                db.add(receipt)
                db.commit()
                record = canonical_record(
                    message_ref_hash=receipt_key,
                    occurred_at=occurred_at,
                    extracted=extracted,
                    attachment_count=attachment_count,
                    sender_address=sender_address,
                )
                result = ingest_canonical_record(db, record)
                receipt.source_record_id = result.source_record_id
                receipt.status = (
                    "ready" if result.processing_status == "ready" else "protected"
                )
                receipt.processed_at = utcnow()
                db.commit()
                reconcile_receipt(
                    db,
                    receipt=receipt,
                    reference_hashes=reply_hashes,
                )
                protected += 1
                if result.processing_status == "ready":
                    ready += 1
                last_uid = uid
            except Exception as error:
                db.rollback()
                failed += 1
                logger.warning(
                    "email_message_processing_failed uid=%s error_type=%s",
                    uid,
                    type(error).__name__,
                )
                # The cursor must never pass a failed delivery. Stop here so the
                # same UID is retried on the next bounded synchronization run.
                break
        state = _state(db)
        state.last_uid = last_uid
        state.last_sync_at = utcnow()
        state.status = "healthy" if failed == 0 else "degraded"
        state.failure_code = None if failed == 0 else "message_processing_failed"
        db.commit()
        return SyncResult(examined, protected, ready, failed, last_uid)
    except Exception:
        db.rollback()
        state = _state(db)
        state.status = "degraded"
        state.failure_code = "email_sync_failed"
        state.last_sync_at = utcnow()
        db.commit()
        raise
    finally:
        if connection is not None:
            try:
                connection.logout()
            except Exception:
                pass
