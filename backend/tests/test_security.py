from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import AuditLogEntry, Base, TokenVaultEntry
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
    assert "AMOUNT_BAND_3_" in sanitized
    assert {entry.entity_type for entry in entries} == {"PHONE", "NRIC", "AMOUNT"}


def test_exact_amount_is_vaulted_and_role_gated():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    raw = "Invoice INV-1024 requires payment of RM 4,500."
    sanitized, entries = tokenize_record(raw, detect_spans(raw), "amount-gate")
    token = next(entry.token for entry in entries if entry.entity_type == "AMOUNT")

    assert token.startswith("AMOUNT_BAND_3_")
    assert "4,500" not in sanitized

    with Session(engine) as db:
        db.add_all(entries)
        db.commit()

        employee = detokenize_response(db, sanitized, "general_employee", "amount-employee")
        finance = detokenize_response(db, sanitized, "finance_ops", "amount-finance")

        assert "RM2.5K–5K" in employee
        assert "4,500" not in employee
        assert "RM 4,500" in finance
        audits = db.scalars(select(AuditLogEntry).order_by(AuditLogEntry.id)).all()
        amount_audits = [entry for entry in audits if entry.token == token]
        assert [entry.authorized for entry in amount_audits] == [False, True]
        assert verify_audit_chain(db)


def test_equivalent_amount_formats_share_token_and_preserve_cents():
    variants = ["RM4,500", "RM 4500.00", "rm4,500.0"]
    tokens = []
    for index, value in enumerate(variants):
        _protected, entries = tokenize_record(value, detect_spans(value), f"amount-{index}")
        tokens.append(next(entry.token for entry in entries if entry.entity_type == "AMOUNT"))
    assert len(set(tokens)) == 1

    protected, entries = tokenize_record("RM 4,500.75", detect_spans("RM 4,500.75"), "cents")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(entries)
        db.commit()
        assert detokenize_response(db, protected, "owner_director", "cents-query") == "RM 4,500.75"


def test_missing_amount_vault_falls_back_to_safe_band():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        rendered = detokenize_response(
            db,
            "Amount AMOUNT_BAND_3_aabbccddee is pending.",
            "owner_director",
            "missing-vault",
        )
    assert rendered == "Amount RM2.5K–5K is pending."


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
