import asyncio
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.integrations.telegram.sender import dispatch_one
from app.models import (
    Base,
    Customer,
    CustomerEndpoint,
    EInvoiceRecord,
    OutreachAction,
    Tenant,
)
from app.security.tokenize import protect_scalar

TENANT = "00000000-0000-0000-0000-000000000001"


def test_dispatch_sends_to_decrypted_chat_and_marks_sent(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(Tenant(id=TENANT, name="Primary", slug="primary"))
    customer = Customer(
        tenant_id=TENANT, canonical_name="Protected", normalized_name="PROTECTED",
        profile_status="confirmed", identity_review_status="clear", profile_origin="telegram",
    )
    db.add(customer)
    db.flush()
    delivery_token = protect_scalar(
        db, entity_type="TGCHAT", value="1001", source_record_id="telegram:test",
        tenant_id=TENANT,
    )
    endpoint = CustomerEndpoint(
        tenant_id=TENANT, customer_id=customer.id, channel="telegram",
        endpoint_token="TGUSER_aaaaaaaaaa", delivery_token=delivery_token,
        verification_status="verified", origin="telegram_onboarding",
    )
    invoice = EInvoiceRecord(
        tenant_id=TENANT, buyer_customer_id=customer.id, supplier_name="FinBrain",
        total_amount=Decimal("950"), status="validated",
        due_date=date.today() - timedelta(days=5),
    )
    db.add_all([endpoint, invoice])
    db.flush()
    action = OutreachAction(
        id="action-1", tenant_id=TENANT, customer_id=customer.id,
        customer_endpoint_id=endpoint.id, channel="telegram", protected_subject="Reminder",
        protected_body="Your invoice is overdue.", status="approved", idempotency_key="key-1",
        created_by_actor_ref="test", origin_type="overdue_invoice",
        origin_invoice_id=invoice.id,
    )
    db.add(action)
    db.commit()
    sent = []

    class Bot:
        async def send_message(self, *, chat_id, text):
            sent.append((chat_id, text))
            return SimpleNamespace(message_id=77)

    monkeypatch.setattr(
        "app.integrations.telegram.sender.get_settings",
        lambda: SimpleNamespace(telegram_outbound_enabled=True),
    )
    try:
        result = asyncio.run(dispatch_one(db, Bot()))
        assert result.id == "action-1"
        assert sent == [(1001, "Your invoice is overdue.")]
        assert action.status == "sent"
        assert action.provider_message_ref_hash is not None
    finally:
        db.close()

