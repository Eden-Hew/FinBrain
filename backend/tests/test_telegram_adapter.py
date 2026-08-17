from datetime import UTC, datetime
from types import SimpleNamespace

from app.integrations.telegram import adapter
from app.integrations.telegram.types import ExtractedContent


def test_telegram_record_ids_are_deterministic_and_opaque(monkeypatch):
    monkeypatch.setattr(
        adapter, "get_settings", lambda: SimpleNamespace(token_root_secret="test-secret")
    )
    first = adapter.opaque_source_id(
        chat_id=123456,
        message_id=99,
        record_type="customer_message",
        stable_content_ref="text",
    )
    second = adapter.opaque_source_id(
        chat_id=123456,
        message_id=99,
        record_type="customer_message",
        stable_content_ref="text",
    )
    assert first == second
    assert first.startswith("telegram:")
    assert "123456" not in first
    assert "99" not in first


def test_canonical_mapping_contains_only_fixed_provenance_keys(monkeypatch):
    monkeypatch.setattr(
        adapter, "get_settings", lambda: SimpleNamespace(token_root_secret="test-secret")
    )
    record = adapter.canonical_record(
        chat_id=123,
        message_id=5,
        record_type="email",
        occurred_at=datetime.now(UTC),
        extracted=ExtractedContent(
            text="Email body",
            input_kind="eml",
            mime_type="message/rfc822",
            filename="customer.eml",
        ),
        stable_content_ref="file-ref",
        forwarded=True,
    )
    assert record.source_system == "telegram"
    assert record.record_type == "email"
    assert set(record.metadata) == {
        "channel",
        "input_kind",
        "forwarded",
        "mime_type",
        "filename",
        "extraction_method",
    }
