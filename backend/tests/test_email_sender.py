from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.integrations.email_connector import sender
from app.models import Base, Customer, OutreachAction, Tenant
from app.schemas import UserRole
from app.services.outreach import (
    create_action,
    register_email_endpoint,
    transition_action,
    verify_endpoint,
)

TENANT = "00000000-0000-0000-0000-000000000001"
USER = "30000000-0000-0000-0000-000000000003"


def _approved_action() -> tuple[Session, OutreachAction]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(Tenant(id=TENANT, name="Test", slug="test"))
    customer = Customer(tenant_id=TENANT, canonical_name="Demo", normalized_name="DEMO")
    db.add(customer)
    db.commit()
    endpoint = register_email_endpoint(
        db, tenant_id=TENANT, customer_id=customer.id, value="recipient@example.com"
    )
    verify_endpoint(db, endpoint.id, tenant_id=TENANT, reviewer_id=USER)
    action = create_action(
        db, tenant_id=TENANT, customer_id=customer.id, endpoint_id=endpoint.id,
        subject="Hello", body="Protected delivery test", idempotency_key="sender-test-001",
        evidence_ids=[], created_by_user_id=USER,
        actor_role=UserRole.FINANCE_OPS.value, actor_ref="finance",
    )
    transition_action(
        db, action.id, "submit", tenant_id=TENANT,
        role=UserRole.FINANCE_OPS, user_id=USER, actor_ref="finance",
    )
    transition_action(
        db, action.id, "approve", tenant_id=TENANT,
        role=UserRole.OWNER_DIRECTOR, user_id=USER, actor_ref="owner",
    )
    return db, db.get(OutreachAction, action.id)


def _settings():
    return SimpleNamespace(
        email_sending_stale_seconds=120, email_smtp_configured=True,
        email_outbound_batch_size=5, token_identity_secret="thread-secret",
        email_smtp_username="sender@example.com", email_imap_username="",
        email_smtp_password="password", email_imap_password="",
        email_smtp_from_address="sender@example.com", email_smtp_host="smtp.test",
        email_smtp_port=587, email_send_timeout_seconds=5,
        email_smtp_use_starttls=True,
    )


def test_dispatch_sends_once_and_records_sent(monkeypatch):
    db, action = _approved_action()
    sent = []

    class SMTP:
        def __init__(self, *_args, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def starttls(self): return None
        def login(self, *_args): return None
        def send_message(self, message): sent.append(message)

    monkeypatch.setattr(sender, "get_settings", _settings)
    monkeypatch.setattr(sender.smtplib, "SMTP", SMTP)
    result = sender.dispatch_one(db)
    assert result is not None and result.status == "sent"
    assert len(sent) == 1
    assert sent[0]["To"] == "recipient@example.com"
    assert result.provider_message_ref_hash
    assert sender.dispatch_one(db) is None
    db.close()


def test_connection_failure_is_failed_and_never_automatically_retried(monkeypatch):
    db, action = _approved_action()

    class SMTP:
        def __init__(self, *_args, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def starttls(self): raise TimeoutError

    monkeypatch.setattr(sender, "get_settings", _settings)
    monkeypatch.setattr(sender.smtplib, "SMTP", SMTP)
    result = sender.dispatch_one(db)
    assert result is not None and result.status == "failed"
    assert result.attempt_count == 1
    assert sender.dispatch_one(db) is None
    db.close()


def test_uncertain_send_failure_is_never_automatically_retried(monkeypatch):
    db, action = _approved_action()

    class SMTP:
        def __init__(self, *_args, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def starttls(self): return None
        def login(self, *_args): return None
        def send_message(self, _message): raise TimeoutError

    monkeypatch.setattr(sender, "get_settings", _settings)
    monkeypatch.setattr(sender.smtplib, "SMTP", SMTP)
    result = sender.dispatch_one(db)
    assert result is not None and result.status == "delivery_unknown"
    assert result.attempt_count == 1
    assert sender.dispatch_one(db) is None
    db.close()
