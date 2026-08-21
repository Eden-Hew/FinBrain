from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import DEFAULT_TENANT_ID, AuditLogEntry, Base, TokenVaultEntry
from app.security.detect import Span, detect_spans
from app.security.detokenize import detokenize_response
from app.security.protection import protect_text
from app.security.tokenize import persist_vault_entries, protect_scalar, tokenize_record
from app.services.audit import verify_audit_chain


def test_tokenization_removes_structured_pii_and_bands_amounts():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    raw = "Call 012-345 6789 about RM4,850; IC 901231-14-5566."
    with Session(engine) as db:
        sanitized, entries = tokenize_record(
            raw, detect_spans(raw), "test-1", DEFAULT_TENANT_ID, db=db
        )

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
    with Session(engine) as db:
        sanitized, entries = tokenize_record(
            raw, detect_spans(raw), "amount-gate", DEFAULT_TENANT_ID, db=db
        )
        token = next(entry.token for entry in entries if entry.entity_type == "AMOUNT")
        assert token.startswith("AMOUNT_BAND_3_")
        assert "4,500" not in sanitized
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
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    variants = ["RM4,500", "RM 4500.00", "rm4,500.0"]
    tokens = []
    with Session(engine) as db:
        for index, value in enumerate(variants):
            _protected, entries = tokenize_record(
                value, detect_spans(value), f"amount-{index}", DEFAULT_TENANT_ID, db=db
            )
            tokens.append(next(entry.token for entry in entries if entry.entity_type == "AMOUNT"))
        assert len(set(tokens)) == 1
        protected, entries = tokenize_record(
            "RM 4,500.75", detect_spans("RM 4,500.75"), "cents", DEFAULT_TENANT_ID, db=db
        )
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
    first, _ = tokenize_record(raw, detect_spans(raw), "one", DEFAULT_TENANT_ID)
    second, _ = tokenize_record(raw, detect_spans(raw), "two", DEFAULT_TENANT_ID)
    assert first == second


def test_repeated_token_before_flush_is_persisted_once():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    raw = "Contact duplicate@example.com"
    with Session(engine) as db:
        _, content_entries = tokenize_record(
            raw, detect_spans(raw), "duplicate-record", DEFAULT_TENANT_ID, db=db
        )
        _, metadata_entries = tokenize_record(
            raw, detect_spans(raw), "duplicate-record", DEFAULT_TENANT_ID, db=db
        )
        persist_vault_entries(db, [*content_entries, *metadata_entries])
        db.commit()

        assert len(db.scalars(select(TokenVaultEntry)).all()) == 1


def test_protection_does_not_tokenize_an_existing_protected_token(monkeypatch):
    token = "ORG_0123456789"
    monkeypatch.setattr(
        "app.security.protection.detect_spans",
        lambda _text: [Span(0, len(token), token, "company name", "test")],
    )

    protected, entries = protect_text(token, "already-protected", DEFAULT_TENANT_ID)

    assert protected == token
    assert entries == []


def test_detokenization_resolves_legacy_nested_tokens():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        inner = protect_scalar(
            db,
            entity_type="ORG",
            value="FinBrain",
            source_record_id="inner-signature",
            tenant_id=DEFAULT_TENANT_ID,
        )
        outer = protect_scalar(
            db,
            entity_type="ORG",
            value=inner,
            source_record_id="outer-signature",
            tenant_id=DEFAULT_TENANT_ID,
        )
        db.commit()

        restored = detokenize_response(db, outer, "owner_director", "nested-signature")

        assert restored == "FinBrain"


def test_role_gate_and_audit_chain():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    raw = "IC 901231-14-5566"
    with Session(engine) as db:
        sanitized, entries = tokenize_record(
            raw, detect_spans(raw), "gate-test", DEFAULT_TENANT_ID, db=db
        )
        db.add_all(entries)
        db.commit()
        token = db.scalar(select(TokenVaultEntry.token))

        employee = detokenize_response(db, sanitized, "general_employee", "query-a")
        assert "******-**-****" in employee
        assert "901231-14-5566" not in employee

        compliance = detokenize_response(db, token, "compliance", "query-b")
        assert compliance == "901231-14-5566"
        assert verify_audit_chain(db)


def test_tokens_do_not_collide_across_tenants():
    """The same raw value tokenized by two different tenants must produce two different
    tokens — otherwise the second tenant's vault write silently no-ops (token already
    exists) and that tenant's disclosure would decrypt to the FIRST tenant's value."""
    raw = "Call 012-345 6789"
    tenant_a_token, _ = tokenize_record(raw, detect_spans(raw), "one", DEFAULT_TENANT_ID)
    tenant_b_token, _ = tokenize_record(
        raw, detect_spans(raw), "two", "00000000-0000-0000-0000-000000000002"
    )
    assert tenant_a_token != tenant_b_token


def test_multiple_disclosures_form_one_continuous_chain():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    raw = "Call 012-345 6789 or email lim.ck@example.com"
    with Session(engine, autoflush=False) as db:
        sanitized, entries = tokenize_record(
            raw, detect_spans(raw), "multi-token-test", DEFAULT_TENANT_ID, db=db
        )
        db.add_all(entries)
        db.commit()
        response = detokenize_response(db, sanitized, "compliance", "query-multi")
        assert "012-345 6789" in response
        assert "lim.ck@example.com" in response
        assert verify_audit_chain(db)
