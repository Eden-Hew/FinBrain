from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.integrations.telegram.onboarding import (
    accept_consent,
    begin_onboarding,
    ingest_customer_message,
    submit_gmail,
    submit_name,
    submit_phone,
)
from app.models import (
    Base,
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
        link = db.scalar(select(CustomerRecordLink).where(
            CustomerRecordLink.tokenized_content_id == row.id
        ))
        assert link is not None
        assert link.match_basis == "verified_telegram_endpoint"
        assert db.get(TelegramOnboardingSession, session.id).status == "completed"
    finally:
        db.close()

