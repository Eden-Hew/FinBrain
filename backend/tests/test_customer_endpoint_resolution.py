from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import (
    Base,
    Customer,
    CustomerEndpoint,
    CustomerIdentityClaim,
    Tenant,
    TokenizedContent,
)
from app.services.customer_endpoint_resolution import EndpointEvidence, resolve_customer_endpoint

TENANT = "00000000-0000-0000-0000-000000000001"


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(Tenant(id=TENANT, name="Primary", slug="primary"))
    db.commit()
    return db


def test_telegram_identity_bundle_creates_one_customer_and_three_endpoints():
    db = _session()
    try:
        content = TokenizedContent(
            tenant_id=TENANT,
            source_record_id="telegram:onboarding-1",
            source_system="telegram",
            record_type="customer_onboarding_profile",
            content_text="PERSON_aaaaaaaaaa EMAIL_bbbbbbbbbb PHONE_cccccccccc",
        )
        db.add(content)
        db.commit()

        result = resolve_customer_endpoint(
            db,
            EndpointEvidence(
                tenant_id=TENANT,
                name_token="PERSON_aaaaaaaaaa",
                email_token="EMAIL_bbbbbbbbbb",
                phone_token="PHONE_cccccccccc",
                telegram_endpoint_token="TELEGRAM_USER_dddddddddd",
                telegram_delivery_token="TELEGRAM_CHAT_eeeeeeeeee",
                evidence_content_id=content.id,
            ),
        )

        assert result.created
        assert db.query(Customer).count() == 1
        endpoints = db.scalars(select(CustomerEndpoint).order_by(CustomerEndpoint.channel)).all()
        assert [(row.channel, row.verification_status) for row in endpoints] == [
            ("email", "observed"),
            ("phone", "observed"),
            ("telegram", "verified"),
        ]
        telegram = next(row for row in endpoints if row.channel == "telegram")
        assert telegram.delivery_token == "TELEGRAM_CHAT_eeeeeeeeee"
        claim = db.scalar(select(CustomerIdentityClaim))
        assert claim is not None
        assert claim.identity_token == "PERSON_aaaaaaaaaa"
        assert claim.status == "accepted"
    finally:
        db.close()


def test_existing_customer_name_conflict_is_recorded_for_owner_review():
    db = _session()
    try:
        existing = Customer(
            tenant_id=TENANT,
            canonical_name="Existing customer",
            normalized_name="EXISTINGCUSTOMER",
            profile_status="confirmed",
            identity_review_status="clear",
            profile_origin="email",
            primary_name_token="PERSON_existing00",
        )
        db.add(existing)
        db.flush()
        db.add(
            CustomerEndpoint(
                tenant_id=TENANT,
                customer_id=existing.id,
                channel="email",
                endpoint_token="EMAIL_bbbbbbbbbb",
                verification_status="verified",
                origin="inbound_email",
            )
        )
        content = TokenizedContent(
            tenant_id=TENANT,
            source_record_id="telegram:onboarding-conflict",
            source_system="telegram",
            record_type="customer_onboarding_profile",
            content_text="PERSON_aaaaaaaaaa EMAIL_bbbbbbbbbb PHONE_cccccccccc",
        )
        db.add(content)
        db.commit()

        result = resolve_customer_endpoint(
            db,
            EndpointEvidence(
                tenant_id=TENANT,
                name_token="PERSON_aaaaaaaaaa",
                email_token="EMAIL_bbbbbbbbbb",
                phone_token="PHONE_cccccccccc",
                telegram_endpoint_token="TELEGRAM_USER_dddddddddd",
                telegram_delivery_token="TELEGRAM_CHAT_eeeeeeeeee",
                evidence_content_id=content.id,
            ),
        )

        db.refresh(existing)
        claim = db.scalar(select(CustomerIdentityClaim))
        phone = _endpoint_for_test(db, "phone")
        assert result.customer_id == existing.id
        assert result.review_required
        assert existing.primary_name_token == "PERSON_existing00"
        assert existing.identity_review_status == "review_required"
        assert claim is not None
        assert claim.identity_token == "PERSON_aaaaaaaaaa"
        assert claim.status == "conflicting"
        assert phone.verification_status == "observed"
        assert phone.origin == "telegram_onboarding"
    finally:
        db.close()


def _endpoint_for_test(db: Session, channel: str) -> CustomerEndpoint:
    row = db.scalar(select(CustomerEndpoint).where(CustomerEndpoint.channel == channel))
    assert row is not None
    return row


def test_existing_email_customer_is_reused_without_duplicate_profile():
    db = _session()
    try:
        existing = Customer(
            tenant_id=TENANT,
            canonical_name="Email contact - BBBBBB",
            normalized_name="EMAILCONTACTBBBBBBBBBB",
            profile_status="provisional",
            profile_origin="email",
        )
        db.add(existing)
        db.flush()
        db.add(
            CustomerEndpoint(
                tenant_id=TENANT,
                customer_id=existing.id,
                channel="email",
                endpoint_token="EMAIL_bbbbbbbbbb",
                verification_status="observed",
                origin="inbound_email",
            )
        )
        content = TokenizedContent(
            tenant_id=TENANT,
            source_record_id="telegram:onboarding-2",
            source_system="telegram",
            record_type="customer_onboarding_profile",
            content_text="protected",
        )
        db.add(content)
        db.commit()

        result = resolve_customer_endpoint(
            db,
            EndpointEvidence(
                tenant_id=TENANT,
                name_token="PERSON_aaaaaaaaaa",
                email_token="EMAIL_bbbbbbbbbb",
                phone_token="PHONE_cccccccccc",
                telegram_endpoint_token="TELEGRAM_USER_dddddddddd",
                telegram_delivery_token="TELEGRAM_CHAT_eeeeeeeeee",
                evidence_content_id=content.id,
            ),
        )

        assert result.customer_id == existing.id
        assert not result.created
        assert db.query(Customer).count() == 1
    finally:
        db.close()
