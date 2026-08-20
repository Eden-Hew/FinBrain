from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.integrations.email_connector import correlation
from app.models import (
    Base,
    Customer,
    CustomerEndpoint,
    CustomerRecordLink,
    EmailIngestionReceipt,
    EmailReplyCorrelation,
    OutreachAction,
    Tenant,
    TokenizedContent,
)

TENANT = "00000000-0000-0000-0000-000000000001"
USER = "30000000-0000-0000-0000-000000000003"


def test_exact_reply_reference_links_customer_and_marks_action_replied(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(Tenant(id=TENANT, name="Test", slug="test"))
    customer = Customer(tenant_id=TENANT, canonical_name="Demo", normalized_name="DEMO")
    db.add(customer)
    db.flush()
    endpoint = CustomerEndpoint(
        tenant_id=TENANT, customer_id=customer.id, channel="email",
        endpoint_token="EMAIL_0123456789", verification_status="verified",
    )
    db.add(endpoint)
    db.flush()
    action = OutreachAction(
        id="action-1", tenant_id=TENANT, customer_id=customer.id,
        customer_endpoint_id=endpoint.id, channel="email",
        protected_subject="Subject", protected_body="Body", status="sent",
        idempotency_key="correlation-test", created_by_user_id=USER,
        provider_message_ref_hash="reference-hash",
    )
    content = TokenizedContent(
        tenant_id=TENANT, source_record_id="email:reply", content_text="Protected reply",
        source_system="email", processing_status="ready",
        safe_metadata={"sender_email": "EMAIL_0123456789"},
    )
    receipt = EmailIngestionReceipt(message_ref_hash="receipt-hash", status="ready")
    db.add_all([action, content, receipt])
    db.commit()
    monkeypatch.setattr(
        correlation, "get_settings",
        lambda: SimpleNamespace(
            email_reply_correlation_enabled=True, customer_attention_enabled=False
        ),
    )
    result = correlation.correlate_reply(
        db, receipt=receipt, protected_row=content,
        reference_hashes=("reference-hash",),
    )
    assert result is not None and result.status == "replied"
    assert receipt.customer_id == customer.id
    assert db.query(EmailReplyCorrelation).count() == 1
    link = db.query(CustomerRecordLink).one()
    assert link.match_status == "verified"
    assert link.match_basis == "exact_email_reply"
    assert link.alias_id is None
    db.close()


def test_reply_reference_with_different_sender_is_flagged_not_replied(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(Tenant(id=TENANT, name="Test", slug="test"))
    customer = Customer(tenant_id=TENANT, canonical_name="Demo", normalized_name="DEMO")
    db.add(customer)
    db.flush()
    endpoint = CustomerEndpoint(
        tenant_id=TENANT, customer_id=customer.id, channel="email",
        endpoint_token="EMAIL_0123456789", verification_status="verified",
    )
    db.add(endpoint)
    db.flush()
    action = OutreachAction(
        id="action-mismatch", tenant_id=TENANT, customer_id=customer.id,
        customer_endpoint_id=endpoint.id, channel="email", protected_subject="Subject",
        protected_body="Body", status="sent", idempotency_key="mismatch-test",
        created_by_user_id=USER, provider_message_ref_hash="reference-hash",
    )
    content = TokenizedContent(
        tenant_id=TENANT, source_record_id="email:mismatch", content_text="Protected reply",
        source_system="email", processing_status="ready",
        safe_metadata={"sender_email": "EMAIL_9999999999"},
    )
    receipt = EmailIngestionReceipt(message_ref_hash="receipt-mismatch", status="ready")
    db.add_all([action, content, receipt])
    db.commit()
    monkeypatch.setattr(
        correlation, "get_settings",
        lambda: SimpleNamespace(
            email_reply_correlation_enabled=True, customer_attention_enabled=False
        ),
    )

    assert correlation.correlate_reply(
        db, receipt=receipt, protected_row=content, reference_hashes=("reference-hash",)
    ) is None
    assert action.status == "sent"
    assert receipt.correlation_status == "identity_conflict"
    assert receipt.customer_id is None
    assert db.query(CustomerRecordLink).count() == 0
    assert db.query(EmailReplyCorrelation).one().status == "identity_conflict"
    db.close()
