from dataclasses import dataclass
from datetime import datetime

from app.schemas import CanonicalIngestionRecord


@dataclass(frozen=True, slots=True)
class ExtractedContent:
    text: str
    input_kind: str
    mime_type: str
    filename: str | None = None
    page_count: int | None = None


@dataclass(slots=True)
class CaptureDraft:
    nonce: str
    telegram_user_id: int
    telegram_chat_id: int
    telegram_message_id: int
    telegram_update_id: int
    record_type: str
    canonical_record: CanonicalIngestionRecord
    protected_preview: str
    source_kind: str
    created_at: datetime
    expires_at_monotonic: float
