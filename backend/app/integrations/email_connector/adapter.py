import hashlib
import hmac
from datetime import datetime

from app.config import get_settings
from app.integrations.telegram.types import ExtractedContent
from app.schemas import CanonicalIngestionRecord


def _digest(value: str, *, purpose: str, length: int = 32) -> str:
    return hmac.new(
        get_settings().token_root_secret.encode(),
        f"{purpose}:{value}".encode(),
        hashlib.sha256,
    ).hexdigest()[:length]


def mailbox_reference(username: str) -> str:
    return _digest(username.casefold(), purpose="email-mailbox")


def message_reference(*, connector_key: str, folder: str, uid: int, message_id: str) -> str:
    return _digest(
        f"{connector_key}|{folder}|{uid}|{message_id}", purpose="email-message", length=64
    )


def canonical_record(
    *,
    message_ref_hash: str,
    occurred_at: datetime | None,
    extracted: ExtractedContent,
    attachment_count: int,
) -> CanonicalIngestionRecord:
    return CanonicalIngestionRecord(
        source_record_id=f"email:{message_ref_hash[:32]}",
        source_system="email",
        record_type="email",
        text=extracted.text,
        occurred_at=occurred_at,
        metadata={
            "channel": "email",
            "input_kind": "email",
            "mime_type": extracted.mime_type,
            "has_attachments": str(attachment_count > 0).lower(),
            "attachment_count": str(attachment_count),
        },
    )
