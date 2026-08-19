import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import (
    DEFAULT_TENANT_ID,
    Base,
    ProtectedTokenRegistry,
    TokenizedContent,
    TokenVaultEntry,
)
from app.schemas import UserRole
from app.security.detect import detect_spans
from app.security.detokenize import TOKEN_PATTERN, detokenize_response
from app.security.tokenize import persist_vault_entries, tokenize_record
from app.services.privacy import erase_token, export_token

RAW_TEXT = "IC 901231-14-5566"
NRIC_VALUE = "901231-14-5566"


def _database() -> tuple:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def _protected_record(db: Session, raw: str, source_record_id: str) -> str:
    sanitized, entries = tokenize_record(
        raw, detect_spans(raw), source_record_id, DEFAULT_TENANT_ID, db=db
    )
    persist_vault_entries(db, entries)
    db.add(TokenizedContent(source_record_id=source_record_id, content_text=sanitized))
    db.commit()
    return sanitized


def _find_nric_token(sanitized: str) -> str:
    return next(t for t in TOKEN_PATTERN.findall(sanitized) if t.startswith("NRIC_"))


def test_export_token_reveals_value_and_lists_referencing_records():
    engine, db = _database()
    try:
        sanitized = _protected_record(db, RAW_TEXT, "msg-1")
        token = _find_nric_token(sanitized)

        result = export_token(
            db,
            token,
            DEFAULT_TENANT_ID,
            role=UserRole.COMPLIANCE,
            query_hash="test-hash",
            actor_ref="test-actor",
        )

        assert result.entity_type == "NRIC"
        assert result.decrypted_value == NRIC_VALUE
        assert result.source_record_ids == ["msg-1"]
    finally:
        db.close()
        engine.dispose()


def test_export_token_withholds_value_when_role_not_allowed():
    engine, db = _database()
    try:
        sanitized = _protected_record(db, RAW_TEXT, "msg-1")
        token = _find_nric_token(sanitized)
        entry = db.get(TokenVaultEntry, token)
        entry.allowed_roles = ["compliance"]  # simulate a stricter policy than NRIC's default
        db.commit()

        result = export_token(
            db,
            token,
            DEFAULT_TENANT_ID,
            role=UserRole.GENERAL_EMPLOYEE,
            query_hash="test-hash",
            actor_ref="test-actor",
        )

        assert result.decrypted_value is None
    finally:
        db.close()
        engine.dispose()


def test_export_token_unknown_token_raises_lookup_error():
    engine, db = _database()
    try:
        with pytest.raises(LookupError):
            export_token(
                db,
                "NRIC_0000000000",
                DEFAULT_TENANT_ID,
                role=UserRole.COMPLIANCE,
                query_hash="test-hash",
                actor_ref="test-actor",
            )
    finally:
        db.close()
        engine.dispose()


def test_erase_token_removes_ciphertext_but_keeps_registry_metadata():
    engine, db = _database()
    try:
        sanitized = _protected_record(db, RAW_TEXT, "msg-1")
        token = _find_nric_token(sanitized)

        result = erase_token(
            db, token, DEFAULT_TENANT_ID, role=UserRole.COMPLIANCE, actor_ref="test-actor"
        )

        assert result.erased is True
        assert db.get(TokenVaultEntry, token) is None
        assert db.get(ProtectedTokenRegistry, token) is not None
    finally:
        db.close()
        engine.dispose()


def test_erase_token_twice_raises_lookup_error():
    engine, db = _database()
    try:
        sanitized = _protected_record(db, RAW_TEXT, "msg-1")
        token = _find_nric_token(sanitized)
        erase_token(db, token, DEFAULT_TENANT_ID, role=UserRole.COMPLIANCE, actor_ref="test-actor")

        with pytest.raises(LookupError):
            erase_token(
                db, token, DEFAULT_TENANT_ID, role=UserRole.COMPLIANCE, actor_ref="test-actor"
            )
    finally:
        db.close()
        engine.dispose()


def test_erased_token_gracefully_masks_in_future_detokenization():
    """After erasure, a chat answer citing this token must never reveal the value
    again -- it degrades to the standard masked placeholder instead of erroring."""
    engine, db = _database()
    try:
        sanitized = _protected_record(db, RAW_TEXT, "msg-1")
        token = _find_nric_token(sanitized)
        erase_token(db, token, DEFAULT_TENANT_ID, role=UserRole.COMPLIANCE, actor_ref="test-actor")

        restored = detokenize_response(db, sanitized, "compliance", "query-hash")

        assert NRIC_VALUE not in restored
        assert "*" in restored
    finally:
        db.close()
        engine.dispose()
