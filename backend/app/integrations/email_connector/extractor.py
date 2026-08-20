import re
from datetime import UTC, datetime
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime

from bs4 import BeautifulSoup

from app.config import get_settings
from app.integrations.telegram.extractors import ExtractionError, extract_document
from app.integrations.telegram.types import ExtractedContent


def extract_reply_references(data: bytes) -> tuple[str, ...]:
    """Return transient RFC message references; callers must hash before persistence."""
    try:
        message = BytesParser(policy=policy.default).parsebytes(data)
    except Exception as error:
        raise ExtractionError("malformed_email") from error
    values: list[str] = []
    for header in (message.get("in-reply-to"), message.get("references")):
        if not header:
            continue
        matches = re.findall(r"<[^>]+>", str(header))
        values.extend(matches or str(header).split())
    return tuple(dict.fromkeys(value.strip() for value in values if value.strip()))


def _text_part(part: Message) -> str:
    try:
        content = str(part.get_content())
    except Exception as error:
        raise ExtractionError("malformed_email") from error
    if part.get_content_type() == "text/html":
        soup = BeautifulSoup(content, "html.parser")
        for element in soup(["script", "style", "form", "noscript"]):
            element.decompose()
        return soup.get_text("\n")
    return content


def _occurred_at(message: Message) -> datetime | None:
    raw = message.get("date")
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except (TypeError, ValueError, OverflowError):
        return None


def _sender_address(message: Message) -> str | None:
    addresses = {
        address.strip().casefold()
        for _name, address in getaddresses(message.get_all("from", []))
        if address.strip() and "@" in address
    }
    return next(iter(addresses)) if len(addresses) == 1 else None


def extract_email(
    data: bytes,
) -> tuple[ExtractedContent, datetime | None, str, int, str | None]:
    try:
        message = BytesParser(policy=policy.default).parsebytes(data)
    except Exception as error:
        raise ExtractionError("malformed_email") from error

    headers = [
        f"{label}: {message.get(name, '')}"
        for label, name in (
            ("Subject", "subject"),
            ("From", "from"),
            ("To", "to"),
            ("Date", "date"),
        )
        if message.get(name)
    ]
    plain: list[str] = []
    html: list[str] = []
    attachments: list[str] = []
    attachment_count = 0
    parts = list(message.walk()) if message.is_multipart() else [message]
    if len(parts) > 200:
        raise ExtractionError("document_expansion_limit")
    for part in parts:
        if part.get_content_disposition() == "attachment":
            attachment_count += 1
            if not get_settings().email_include_attachments:
                continue
            filename = part.get_filename() or "attachment"
            payload = part.get_payload(decode=True) or b""
            try:
                extracted = extract_document(
                    payload,
                    filename=filename,
                    mime_type=part.get_content_type(),
                )
            except ExtractionError:
                continue
            attachments.append(f"Attachment: {filename}\n{extracted.text}")
            continue
        content_type = part.get_content_type()
        if content_type == "text/plain":
            plain.append(_text_part(part))
        elif content_type == "text/html":
            html.append(_text_part(part))

    body = "\n".join(plain or html).strip()
    combined = "\n".join(headers + ([""] if headers and body else []) + [body] + attachments)
    combined = combined.replace("\x00", "").strip()
    if not combined:
        raise ExtractionError("no_extractable_text")
    if len(combined) > get_settings().telegram_max_extracted_chars:
        raise ExtractionError("extracted_text_too_large")
    message_id = str(message.get("message-id") or "missing-message-id")
    return (
        ExtractedContent(text=combined, input_kind="email", mime_type="message/rfc822"),
        _occurred_at(message),
        message_id,
        attachment_count,
        _sender_address(message),
    )
