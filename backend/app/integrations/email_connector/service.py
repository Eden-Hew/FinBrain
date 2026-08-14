import imaplib
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.email_connector.adapter import (
    canonical_record,
    mailbox_reference,
    message_reference,
)
from app.integrations.email_connector.extractor import extract_email
from app.models import EmailIngestionReceipt, EmailSyncState, utcnow
from app.services.ingestion import ingest_canonical_record


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


def sync_mailbox(db: Session) -> SyncResult:
    settings = get_settings()
    if not settings.email_configured:
        raise RuntimeError("Email connector is not configured")
    state = _state(db)
    state.status = "syncing"
    state.failure_code = None
    db.commit()
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
                extracted, occurred_at, message_id, attachment_count = extract_email(raw_message)
                receipt_key = message_reference(
                    connector_key=state.connector_key,
                    folder=state.folder_name,
                    uid=uid,
                    message_id=message_id,
                )
                receipt = db.get(EmailIngestionReceipt, receipt_key)
                if receipt is not None:
                    last_uid = uid
                    continue
                receipt = EmailIngestionReceipt(
                    message_ref_hash=receipt_key,
                    status="received",
                )
                db.add(receipt)
                db.commit()
                record = canonical_record(
                    message_ref_hash=receipt_key,
                    occurred_at=occurred_at,
                    extracted=extracted,
                    attachment_count=attachment_count,
                )
                result = ingest_canonical_record(db, record)
                receipt.source_record_id = result.source_record_id
                receipt.status = (
                    "ready" if result.processing_status == "ready" else "protected"
                )
                receipt.processed_at = utcnow()
                db.commit()
                protected += 1
                if result.processing_status == "ready":
                    ready += 1
                last_uid = uid
            except Exception:
                db.rollback()
                failed += 1
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
