from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, TokenVaultEntry
from app.security.detect import detect_spans
from app.security.detokenize import detokenize_response
from app.security.tokenize import tokenize_record
from app.services.audit import verify_audit_chain


def test_tokenization_removes_structured_pii_and_bands_amounts():
    raw = "Call 012-345 6789 about RM4,850; IC 901231-14-5566."
    sanitized, entries = tokenize_record(raw, detect_spans(raw), "test-1")

    assert "012-345 6789" not in sanitized
    assert "901231-14-5566" not in sanitized
    assert "RM4,850" not in sanitized
    assert "PHONE_" in sanitized
    assert "NRIC_" in sanitized
    assert "AMOUNT_BAND_3" in sanitized
    assert {entry.entity_type for entry in entries} == {"PHONE", "NRIC"}


def test_deterministic_tokens_link_same_value():
    raw = "Contact lim.ck@example.com"
    first, _ = tokenize_record(raw, detect_spans(raw), "one")
    second, _ = tokenize_record(raw, detect_spans(raw), "two")
    assert first == second


def test_role_gate_and_audit_chain():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    raw = "IC 901231-14-5566"
    sanitized, entries = tokenize_record(raw, detect_spans(raw), "gate-test")

    with Session(engine) as db:
        db.add_all(entries)
        db.commit()
        token = db.scalar(select(TokenVaultEntry.token))

        employee = detokenize_response(db, sanitized, "general_employee", "query-a")
        assert "restricted" in employee
        assert "901231-14-5566" not in employee

        compliance = detokenize_response(db, token, "compliance", "query-b")
        assert compliance == "901231-14-5566"
        assert verify_audit_chain(db)


def test_multiple_disclosures_form_one_continuous_chain():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    raw = "Call 012-345 6789 or email lim.ck@example.com"
    sanitized, entries = tokenize_record(raw, detect_spans(raw), "multi-token-test")

    with Session(engine, autoflush=False) as db:
        db.add_all(entries)
        db.commit()
        response = detokenize_response(db, sanitized, "compliance", "query-multi")
        assert "012-345 6789" in response
        assert "lim.ck@example.com" in response
        assert verify_audit_chain(db)
