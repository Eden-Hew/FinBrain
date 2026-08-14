from email.message import EmailMessage
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.integrations.email_connector import service
from app.integrations.email_connector.adapter import canonical_record, message_reference
from app.integrations.email_connector.extractor import extract_email
from app.models import Base, EmailSyncState


def _message() -> bytes:
    message = EmailMessage()
    message["Subject"] = "Delayed invoice for Ahmad"
    message["From"] = "ahmad@example.com"
    message["To"] = "finance@example.com"
    message["Message-ID"] = "<example-1@example.com>"
    message.set_content("Please call 012-345 6789 about the overdue approval.")
    return message.as_bytes()


def test_email_extraction_normalizes_to_canonical_record():
    extracted, occurred_at, message_id, attachment_count = extract_email(_message())
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
    )

    assert record.source_record_id.startswith("email:")
    assert "ahmad@example.com" in record.text
    assert record.source_system == "email"
    assert record.metadata["has_attachments"] == "false"


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
