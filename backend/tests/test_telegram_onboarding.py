from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.integrations.telegram.onboarding import (
    accept_consent,
    begin_onboarding,
    cancel_onboarding,
    customer_display_name,
    ingest_customer_message,
    submit_gmail,
    submit_name,
    submit_phone,
)
from app.models import (
    Base,
    Customer,
    CustomerEndpoint,
    CustomerIdentityClaim,
    CustomerRecordLink,
    TelegramOnboardingSession,
    Tenant,
    TokenizedContent,
)

TENANT = "00000000-0000-0000-0000-000000000001"


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(Tenant(id=TENANT, name="Primary", slug="primary"))
    db.commit()
    return db


def test_guided_onboarding_unifies_identity_before_accepting_messages(monkeypatch):
    db = _session()
    monkeypatch.setattr(
        "app.integrations.telegram.onboarding.enrich_protected_record",
        lambda _db, source_record_id, **_kwargs: None,
    )
    try:
        session = begin_onboarding(db, tenant_id=TENANT, user_id=1001, chat_id=1001)
        assert session.status == "awaiting_consent"
        assert accept_consent(db, session.id).status == "awaiting_name"
        assert submit_name(db, session.id, "Aisha Rahman").status == "awaiting_gmail"
        assert submit_gmail(db, session.id, "aisha@gmail.com").status == "awaiting_phone"
        completed = submit_phone(db, session.id, "+60123456789")

        assert completed.status == "awaiting_message"
        assert completed.customer_id is not None
        assert customer_display_name(db, completed) == "Aisha Rahman"
        profiles = db.scalars(
            select(TokenizedContent).where(
                TokenizedContent.record_type == "customer_onboarding_profile"
            )
        ).all()
        assert len(profiles) == 1
        assert "aisha@gmail.com" not in profiles[0].content_text
        assert "Aisha Rahman" not in profiles[0].content_text
        assert db.scalar(select(CustomerRecordLink)).tokenized_content_id == profiles[0].id
    finally:
        db.close()


def test_customer_message_is_ingested_and_linked_after_onboarding(monkeypatch):
    db = _session()
    monkeypatch.setattr(
        "app.integrations.telegram.onboarding.enrich_protected_record",
        lambda _db, source_record_id, **_kwargs: None,
    )
    try:
        session = begin_onboarding(db, tenant_id=TENANT, user_id=1001, chat_id=1001)
        accept_consent(db, session.id)
        submit_name(db, session.id, "Aisha Rahman")
        submit_gmail(db, session.id, "aisha@gmail.com")
        submit_phone(db, session.id, "+60123456789")

        row = ingest_customer_message(
            db,
            session_id=session.id,
            message_id=55,
            text="My invoice is incorrect.",
        )

        assert row.record_type == "customer_message"
        link = db.scalar(
            select(CustomerRecordLink).where(CustomerRecordLink.tokenized_content_id == row.id)
        )
        assert link is not None
        assert link.match_basis == "verified_telegram_endpoint"
        assert db.get(TelegramOnboardingSession, session.id).status == "completed"
    finally:
        db.close()


def test_start_recovers_an_interrupted_reconciliation_at_phone_step():
    db = _session()
    try:
        session = begin_onboarding(db, tenant_id=TENANT, user_id=1001, chat_id=1001)
        accept_consent(db, session.id)
        submit_name(db, session.id, "Aisha Rahman")
        submit_gmail(db, session.id, "aisha@gmail.com")
        session.status = "reconciling"
        db.commit()

        resumed = begin_onboarding(db, tenant_id=TENANT, user_id=1001, chat_id=1001)

        assert resumed.status == "awaiting_phone"
        assert resumed.name_token is not None
        assert resumed.email_token is not None
        assert resumed.failure_code == "telegram_reconciliation_interrupted"
    finally:
        db.close()


def test_start_repairs_completed_legacy_identity_claim(monkeypatch):
    db = _session()
    monkeypatch.setattr(
        "app.integrations.telegram.onboarding.enrich_protected_record",
        lambda _db, source_record_id, **_kwargs: None,
    )
    try:
        session = begin_onboarding(db, tenant_id=TENANT, user_id=1001, chat_id=1001)
        accept_consent(db, session.id)
        submit_name(db, session.id, "Aisha Rahman")
        submit_gmail(db, session.id, "aisha@gmail.com")
        completed = submit_phone(db, session.id, "+60123456789")
        customer = db.get(Customer, completed.customer_id)
        assert customer is not None
        claim = db.scalar(select(CustomerIdentityClaim))
        telegram = db.scalar(select(CustomerEndpoint).where(CustomerEndpoint.channel == "telegram"))
        phone = db.scalar(select(CustomerEndpoint).where(CustomerEndpoint.channel == "phone"))
        assert claim is not None
        assert telegram is not None
        assert phone is not None

        db.delete(claim)
        phone.verification_status = "verified"
        phone.origin = "telegram_contact_share"
        db.commit()

        repaired = begin_onboarding(db, tenant_id=TENANT, user_id=1001, chat_id=1001)

        repaired_claim = db.scalar(select(CustomerIdentityClaim))
        assert repaired.id == completed.id
        assert repaired_claim is not None
        assert repaired_claim.identity_token == completed.name_token
        assert phone.verification_status == "observed"
        assert phone.origin == "telegram_onboarding"
    finally:
        db.close()


def test_cancelled_onboarding_restarts_from_name_step():
    db = _session()
    try:
        session = begin_onboarding(db, tenant_id=TENANT, user_id=1001, chat_id=1001)
        accept_consent(db, session.id)
        submit_name(db, session.id, "Aisha Rahman")
        cancel_onboarding(db, session.id)

        restarted = begin_onboarding(db, tenant_id=TENANT, user_id=1001, chat_id=1001)

        assert restarted.status == "awaiting_consent"
        assert accept_consent(db, restarted.id).status == "awaiting_name"
    finally:
        db.close()
