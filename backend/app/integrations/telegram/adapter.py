import hashlib
import hmac
from datetime import datetime

from app.config import get_settings
from app.integrations.telegram.types import ExtractedContent
from app.schemas import CanonicalIngestionRecord

RECORD_TYPES = {
    "customer": "customer_message",
    "transaction": "transaction_note",
    "email": "email",
    "document": "document_text",
}


def opaque_source_id(
    *, chat_id: int, message_id: int, record_type: str, stable_content_ref: str
) -> str:
    payload = f"{chat_id}|{message_id}|{stable_content_ref}|{record_type}"
    digest = hmac.new(
        get_settings().token_root_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()[:32]
    return f"telegram:{digest}"


def canonical_record(
    *,
    chat_id: int,
    message_id: int,
    record_type: str,
    occurred_at: datetime,
    extracted: ExtractedContent,
    stable_content_ref: str,
    forwarded: bool = False,
    caption: str | None = None,
) -> CanonicalIngestionRecord:
    metadata = {
        "channel": "telegram_private",
        "input_kind": extracted.input_kind,
        "forwarded": str(forwarded).lower(),
        "mime_type": extracted.mime_type,
        "extraction_method": extracted.extraction_method or "text",
    }
    if extracted.filename:
        metadata["filename"] = extracted.filename
    if extracted.page_count is not None:
        metadata["page_count"] = str(extracted.page_count)
    if caption:
        metadata["telegram_caption"] = caption
    return CanonicalIngestionRecord(
        source_record_id=opaque_source_id(
            chat_id=chat_id,
            message_id=message_id,
            record_type=record_type,
            stable_content_ref=stable_content_ref,
        ),
        source_system="telegram",
        record_type=record_type,
        text=extracted.text,
        occurred_at=occurred_at,
        metadata=metadata,
    )


def short_reference(source_record_id: str) -> str:
    return f"TG-{source_record_id.rsplit(':', 1)[-1][:6].upper()}"
