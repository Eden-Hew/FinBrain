from email.message import EmailMessage
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.integrations.email_connector import service
from app.integrations.email_connector.adapter import canonical_record, message_reference
from app.integrations.email_connector.extractor import extract_email, extract_reply_references
from app.models import Base, EmailSyncState


def _message() -> bytes:
    message = EmailMessage()
    message["Subject"] = "Delayed invoice for Ahmad"
    message["From"] = "Ahmad Rahman <ahmad@example.com>"
    message["To"] = "finance@example.com"
    message["Message-ID"] = "<example-1@example.com>"
    message.set_content("Please call 012-345 6789 about the overdue approval.")
    return message.as_bytes()


def test_email_extraction_normalizes_to_canonical_record():
    extracted, occurred_at, message_id, attachment_count, sender_address = extract_email(
        _message()
    )
    reference = message_reference(
        connector_key="imap-primary",
        folder="INBOX",
        uid=10,
        message_id=message_id,
    )
    record = canonical_record(
        message_ref_hash=reference,
        occurred_at=occurred_at,
        extracted=extracted,
        attachment_count=attachment_count,
        sender_address=sender_address,
    )

    assert record.source_record_id.startswith("email:")
    assert "ahmad@example.com" in record.text
    assert record.metadata["sender_email"] == "ahmad@example.com"
    assert record.source_system == "email"
    assert record.metadata["has_attachments"] == "false"


def test_email_extraction_gets_bare_sender_without_guessing_a_name():
    message = EmailMessage()
    message["From"] = "bare.sender@example.com"
    message["To"] = "finance@example.com"
    message.set_content("No person name appears in this email.")

    extracted, _occurred_at, _message_id, _attachments, sender_address = extract_email(
        message.as_bytes()
    )

    assert sender_address == "bare.sender@example.com"
    assert "bare.sender@example.com" in extracted.text


def test_email_extraction_rejects_ambiguous_sender_headers():
    raw = (
        b"From: first@example.com, second@example.com\r\n"
        b"To: finance@example.com\r\n"
        b"Content-Type: text/plain\r\n\r\nMessage"
    )
    _extracted, _occurred_at, _message_id, _attachments, sender_address = extract_email(raw)
    assert sender_address is None


def test_email_reference_is_deterministic_and_hides_message_id():
    first = message_reference(
        connector_key="imap-primary", folder="INBOX", uid=10, message_id="private@example.com"
    )
    second = message_reference(
        connector_key="imap-primary", folder="INBOX", uid=10, message_id="private@example.com"
    )

    assert first == second
    assert "private" not in first
    assert len(first) == 64


def test_reply_headers_are_extracted_only_for_immediate_hashing():
    message = EmailMessage()
    message["From"] = "customer@example.com"
    message["To"] = "finance@example.com"
    message["In-Reply-To"] = "<sent-1@finbrain.local>"
    message["References"] = "<older@finbrain.local> <sent-1@finbrain.local>"
    message.set_content("Reply")
    assert extract_reply_references(message.as_bytes()) == (
        "<sent-1@finbrain.local>",
        "<older@finbrain.local>",
    )


def test_email_search_is_unread_and_incremental():
    assert service._unread_search_criteria(0) == ("UNSEEN",)
    assert service._unread_search_criteria(41) == ("UNSEEN", "UID 42:*")
    assert service._new_uid_values(b"41 42 43", last_uid=41, limit=25) == [42, 43]
    assert service._new_uid_values(b"51", last_uid=51, limit=25) == []


class _FailingMailbox:
    def login(self, *_):
        return "OK", []

    def select(self, *_args, **_kwargs):
        return "OK", []

    def uid(self, command, *_args):
        if command == "search":
            return "OK", [b"11 12"]
        return "OK", [(b"11 (RFC822 {7})", b"message")]

    def logout(self):
        return "BYE", []


def test_failed_email_does_not_advance_incremental_cursor(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = SimpleNamespace(
        email_configured=True,
        email_imap_username="private@example.com",
        email_imap_folder="INBOX",
        email_max_messages_per_sync=25,
        token_root_secret="test-secret-that-is-longer-than-32-characters",
    )
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    monkeypatch.setattr(service, "_connect", _FailingMailbox)
    monkeypatch.setattr(
        service,
        "extract_email",
        lambda _raw: (_ for _ in ()).throw(ValueError("parse failed")),
    )

    with Session(engine) as db:
        result = service.sync_mailbox(db)
        state = db.get(EmailSyncState, "imap-primary")

        assert result.examined == 1
        assert result.failed == 1
        assert result.last_uid == 0
        assert state is not None
        assert state.last_uid == 0
        assert state.status == "degraded"
