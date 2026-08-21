from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, Customer, CustomerEndpoint
from app.schemas import EInvoiceCreatePayload, UserRole
from app.security.tokenize import derive_token
from app.services.einvoice_readiness import create_record
from app.services.entity_resolution import normalize_business_name, resolve_customer

TENANT_A = "00000000-0000-0000-0000-0000000000a1"
TENANT_B = "00000000-0000-0000-0000-0000000000b2"


def test_normalize_business_name_collapses_suffix_and_punctuation_variants():
    assert normalize_business_name("Acme Sdn Bhd") == normalize_business_name("ACME SDN. BHD.")
    assert normalize_business_name("Acme Trading Enterprise") == normalize_business_name("Acme")


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_resolve_customer_finds_existing_row_for_a_name_variant():
    db = _session()
    try:
        first = resolve_customer(db, TENANT_A, "Acme Sdn Bhd")
        second = resolve_customer(db, TENANT_A, "ACME SDN. BHD.")
        assert first is not None
        assert second is not None
        assert first.id == second.id
        assert db.query(Customer).count() == 1
    finally:
        db.close()


def test_resolve_customer_is_isolated_per_tenant():
    db = _session()
    try:
        a = resolve_customer(db, TENANT_A, "Acme Sdn Bhd")
        b = resolve_customer(db, TENANT_B, "Acme Sdn Bhd")
        assert a is not None
        assert b is not None
        assert a.id != b.id
        assert a.tenant_id != b.tenant_id
    finally:
        db.close()


def test_resolve_customer_returns_none_for_a_name_with_nothing_left_after_normalizing():
    db = _session()
    try:
        assert resolve_customer(db, TENANT_A, "Sdn Bhd") is None
        assert resolve_customer(db, TENANT_A, "   ") is None
        assert db.query(Customer).count() == 0
    finally:
        db.close()


def _payload(buyer_name: str | None) -> EInvoiceCreatePayload:
    return EInvoiceCreatePayload(
        supplier_name="My Business Sdn Bhd",
        supplier_tin="C1234567890",
        buyer_name=buyer_name,
        total_amount=Decimal("100.00"),
    )


def test_create_record_links_buyer_name_variants_to_the_same_customer(monkeypatch):
    monkeypatch.setenv("MORPHEUS_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    db = _session()
    try:
        first = create_record(
            db,
            _payload("Acme Sdn Bhd"),
            role=UserRole.OWNER_DIRECTOR,
            actor_ref="test-actor",
            tenant_id=TENANT_A,
        )
        second = create_record(
            db,
            _payload("ACME SDN. BHD."),
            role=UserRole.OWNER_DIRECTOR,
            actor_ref="test-actor",
            tenant_id=TENANT_A,
        )
        assert first.buyer_customer_id is not None
        assert first.buyer_customer_id == second.buyer_customer_id
        assert db.query(Customer).count() == 1
    finally:
        db.close()


def test_create_record_without_buyer_name_has_no_customer_link(monkeypatch):
    monkeypatch.setenv("MORPHEUS_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    db = _session()
    try:
        record = create_record(
            db,
            _payload(None),
            role=UserRole.OWNER_DIRECTOR,
            actor_ref="test-actor",
            tenant_id=TENANT_A,
        )
        assert record.buyer_customer_id is None
    finally:
        db.close()


def test_create_record_matches_existing_email_endpoint_case_insensitively(monkeypatch):
    monkeypatch.setenv("MORPHEUS_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    db = _session()
    try:
        customer = Customer(
            tenant_id=TENANT_A,
            canonical_name="Email customer",
            normalized_name="EMAILCUSTOMER",
            profile_status="confirmed",
        )
        db.add(customer)
        db.flush()
        db.add(CustomerEndpoint(
            tenant_id=TENANT_A,
            customer_id=customer.id,
            channel="email",
            endpoint_token=derive_token("EMAIL", "buyer@gmail.com", TENANT_A),
            verification_status="observed",
            origin="telegram_onboarding",
        ))
        db.commit()

        payload = _payload("Different Display Name")
        payload.buyer_email = "  BUYER@GMAIL.COM  "
        record = create_record(
            db,
            payload,
            role=UserRole.OWNER_DIRECTOR,
            actor_ref="test-actor",
            tenant_id=TENANT_A,
        )

        assert record.buyer_customer_id == customer.id
    finally:
        db.close()
