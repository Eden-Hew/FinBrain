import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.integrations.email_connector.identity import link_verified_sender
from app.models import (
    Base,
    Customer,
    CustomerEndpoint,
    CustomerIdentityClaim,
    CustomerRecordLink,
    EmailIngestionReceipt,
    Tenant,
    TokenizedContent,
)

TENANT = "00000000-0000-0000-0000-000000000001"
OTHER_TENANT = "00000000-0000-0000-0000-000000000002"
TOKEN = "EMAIL_0123456789"


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add_all([
        Tenant(id=TENANT, name="Primary", slug="primary"),
        Tenant(id=OTHER_TENANT, name="Other", slug="other"),
    ])
    db.commit()
    return db


def _customer(db: Session, tenant_id: str, name: str) -> Customer:
    row = Customer(
        tenant_id=tenant_id,
        canonical_name=name,
        normalized_name=name.upper().replace(" ", ""),
    )
    db.add(row)
    db.commit()
    return row


def _email_rows(db: Session) -> tuple[EmailIngestionReceipt, TokenizedContent]:
    content = TokenizedContent(
        tenant_id=TENANT,
        source_record_id="email:sender-match",
        source_system="email",
        record_type="email",
        content_text="No explicit customer name appears here.",
        safe_metadata={"sender_email": TOKEN},
        processing_status="ready",
    )
    receipt = EmailIngestionReceipt(message_ref_hash="receipt-sender-match")
    db.add_all([content, receipt])
    db.commit()
    return receipt, content


def test_verified_sender_endpoint_creates_exact_customer_link(monkeypatch):
    db = _session()
    try:
        monkeypatch.setattr(
            "app.integrations.email_connector.identity.get_settings",
            lambda: type("Settings", (), {"customer_attention_enabled": False})(),
        )
        customer = _customer(db, TENANT, "Known Customer")
        db.add(CustomerEndpoint(
            tenant_id=TENANT, customer_id=customer.id, channel="email",
            endpoint_token=TOKEN, verification_status="verified",
        ))
        receipt, content = _email_rows(db)

        matched = link_verified_sender(db, receipt=receipt, protected_row=content)

        link = db.scalar(select(CustomerRecordLink))
        assert matched == customer.id
        assert receipt.customer_id == customer.id
        assert link is not None
        assert link.match_status == "verified"
        assert link.match_basis == "exact_verified_email_endpoint"
    finally:
        db.close()


def test_unverified_unknown_and_cross_tenant_endpoints_do_not_link(monkeypatch):
    db = _session()
    try:
        monkeypatch.setattr(
            "app.integrations.email_connector.identity.get_settings",
            lambda: type("Settings", (), {"customer_attention_enabled": False})(),
        )
        observed = _customer(db, TENANT, "Observed Customer")
        other = _customer(db, OTHER_TENANT, "Other Customer")
        db.add_all([
            CustomerEndpoint(
                tenant_id=TENANT, customer_id=observed.id, channel="email",
                endpoint_token=TOKEN, verification_status="observed",
            ),
            CustomerEndpoint(
                tenant_id=OTHER_TENANT, customer_id=other.id, channel="email",
                endpoint_token=TOKEN, verification_status="verified",
            ),
        ])
        receipt, content = _email_rows(db)

        assert link_verified_sender(db, receipt=receipt, protected_row=content) is None
        assert receipt.customer_id is None
        assert db.scalar(select(CustomerRecordLink)) is None
    finally:
        db.close()


def test_sender_token_shared_by_multiple_customers_is_ambiguous(monkeypatch):
    db = _session()
    try:
        monkeypatch.setattr(
            "app.integrations.email_connector.identity.get_settings",
            lambda: type("Settings", (), {"customer_attention_enabled": False})(),
        )
        first = _customer(db, TENANT, "First Customer")
        second = _customer(db, TENANT, "Second Customer")
        db.add_all([
            CustomerEndpoint(
                tenant_id=TENANT, customer_id=first.id, channel="email",
                endpoint_token=TOKEN, verification_status="verified",
            ),
            CustomerEndpoint(
                tenant_id=TENANT, customer_id=second.id, channel="email",
                endpoint_token=TOKEN, verification_status="verified",
            ),
        ])
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.close()


def test_unknown_sender_creates_one_provisional_profile_and_reuses_it(monkeypatch):
    db = _session()
    try:
        monkeypatch.setattr(
            "app.integrations.email_connector.identity.get_settings",
            lambda: type("Settings", (), {"customer_attention_enabled": False})(),
        )
        receipt, content = _email_rows(db)

        customer_id = link_verified_sender(db, receipt=receipt, protected_row=content)

        customer = db.get(Customer, customer_id)
        endpoint = db.scalar(select(CustomerEndpoint))
        assert customer is not None
        assert customer.profile_status == "provisional"
        assert customer.profile_origin == "email"
        assert customer.canonical_name.startswith("Email contact - ")
        assert endpoint is not None
        assert endpoint.origin == "inbound_email"
        assert endpoint.verification_status == "observed"

        second = TokenizedContent(
            tenant_id=TENANT,
            source_record_id="email:sender-match-2",
            source_system="email",
            record_type="email",
            content_text="A later message from the same protected sender.",
            safe_metadata={"sender_email": TOKEN},
            processing_status="ready",
        )
        second_receipt = EmailIngestionReceipt(message_ref_hash="receipt-sender-match-2")
        db.add_all([second, second_receipt])
        db.commit()
        assert link_verified_sender(
            db, receipt=second_receipt, protected_row=second
        ) == customer_id
        assert db.query(Customer).filter(Customer.tenant_id == TENANT).count() == 1
        assert db.query(CustomerEndpoint).filter(CustomerEndpoint.tenant_id == TENANT).count() == 1
    finally:
        db.close()


def test_protected_from_header_recovers_sender_metadata(monkeypatch):
    db = _session()
    try:
        monkeypatch.setattr(
            "app.integrations.email_connector.identity.get_settings",
            lambda: type("Settings", (), {"customer_attention_enabled": False})(),
        )
        receipt, content = _email_rows(db)
        content.safe_metadata = {"channel": "email"}
        content.content_text = "From: PERSON_aaaaaaaaaa <EMAIL_0123456789>\nProtected body"
        db.commit()

        customer_id = link_verified_sender(db, receipt=receipt, protected_row=content)

        assert customer_id is not None
        assert content.safe_metadata["sender_email"] == TOKEN
        assert receipt.customer_id == customer_id
        assert db.scalar(select(CustomerEndpoint)).endpoint_token == TOKEN
    finally:
        db.close()


def test_attention_failure_does_not_undo_email_customer_link(monkeypatch):
    db = _session()
    try:
        monkeypatch.setattr(
            "app.integrations.email_connector.identity.get_settings",
            lambda: type("Settings", (), {"customer_attention_enabled": True})(),
        )

        def fail_attention(*_args, **_kwargs):
            raise RuntimeError("attention unavailable")

        monkeypatch.setattr(
            "app.services.customer_attention.recalculate_customer_attention",
            fail_attention,
        )
        receipt, content = _email_rows(db)

        customer_id = link_verified_sender(db, receipt=receipt, protected_row=content)

        assert customer_id is not None
        assert receipt.customer_id == customer_id
        assert db.get(Customer, customer_id) is not None
        assert db.scalar(select(CustomerRecordLink)) is not None
    finally:
        db.close()


def test_self_identification_is_protected_claim_and_name_change_requires_review(monkeypatch):
    db = _session()
    try:
        monkeypatch.setattr(
            "app.integrations.email_connector.identity.get_settings",
            lambda: type("Settings", (), {"customer_attention_enabled": False})(),
        )
        receipt, content = _email_rows(db)
        content.content_text = "From: PERSON_aaaaaaaaaa <EMAIL_0123456789>\nI am PERSON_aaaaaaaaaa."
        db.commit()
        customer_id = link_verified_sender(db, receipt=receipt, protected_row=content)
        customer = db.get(Customer, customer_id)
        assert customer.primary_name_token == "PERSON_aaaaaaaaaa"
        assert customer.identity_review_status == "clear"

        second = TokenizedContent(
            tenant_id=TENANT,
            source_record_id="email:name-conflict",
            source_system="email",
            record_type="email",
            content_text="From: PERSON_bbbbbbbbbb <EMAIL_0123456789>\nI am PERSON_bbbbbbbbbb.",
            safe_metadata={"sender_email": TOKEN},
            processing_status="ready",
        )
        second_receipt = EmailIngestionReceipt(message_ref_hash="receipt-name-conflict")
        db.add_all([second, second_receipt])
        db.commit()
        link_verified_sender(db, receipt=second_receipt, protected_row=second)
        db.refresh(customer)
        assert customer.primary_name_token == "PERSON_aaaaaaaaaa"
        assert customer.identity_review_status == "review_required"
        assert db.query(CustomerIdentityClaim).filter_by(status="conflicting").count() >= 1
    finally:
        db.close()
