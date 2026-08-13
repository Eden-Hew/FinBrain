import time
from datetime import UTC, datetime
from types import SimpleNamespace

from app.integrations.telegram import drafts
from app.integrations.telegram.types import CaptureDraft
from app.schemas import CanonicalIngestionRecord


def _draft(nonce: str, expires: float) -> CaptureDraft:
    return CaptureDraft(
        nonce=nonce,
        telegram_user_id=123,
        telegram_chat_id=123,
        telegram_message_id=9,
        telegram_update_id=19,
        record_type="customer_message",
        canonical_record=CanonicalIngestionRecord(
            source_record_id="telegram:abc",
            source_system="telegram",
            record_type="customer_message",
            text="raw draft",
        ),
        protected_preview="protected draft",
        source_kind="text",
        created_at=datetime.now(UTC),
        expires_at_monotonic=expires,
    )


def test_draft_store_replaces_and_expires():
    store = drafts.DraftStore()
    store.put(_draft("first", time.monotonic() + 60))
    store.put(_draft("second", time.monotonic() + 60))
    assert store.get(123).nonce == "second"
    assert store.pop(123, "wrong") is None
    assert store.pop(123, "second").nonce == "second"
    store.put(_draft("expired", time.monotonic() - 1))
    assert store.get(123) is None


def test_callback_signature_rejects_wrong_user(monkeypatch):
    monkeypatch.setattr(
        drafts, "get_settings", lambda: SimpleNamespace(token_root_secret="test-secret")
    )
    callback = drafts.sign_callback("confirm", "nonce", 123)
    assert drafts.verify_callback(callback, 123) == ("confirm", "nonce")
    assert drafts.verify_callback(callback, 124) is None
