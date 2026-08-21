from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import (
    Base,
    Customer,
    CustomerEndpoint,
    EInvoiceRecord,
    OutreachAction,
    Tenant,
    TenantOutreachPolicy,
)
from app.services.overdue_reminders import plan_due_reminders

TENANT = "00000000-0000-0000-0000-000000000001"


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    db.add(Tenant(id=TENANT, name="Primary", slug="primary"))
    db.commit()
    return db


def test_overdue_invoice_creates_one_idempotent_telegram_action():
    db = _session()
    try:
        customer = Customer(
            tenant_id=TENANT, canonical_name="Protected customer", normalized_name="CUSTOMER",
            profile_status="confirmed", identity_review_status="clear", profile_origin="telegram",
        )
        db.add(customer)
        db.flush()
        endpoint = CustomerEndpoint(
            tenant_id=TENANT, customer_id=customer.id, channel="telegram",
            endpoint_token="TGUSER_aaaaaaaaaa", delivery_token="TGCHAT_bbbbbbbbbb",
            verification_status="verified", origin="telegram_onboarding",
        )
        invoice = EInvoiceRecord(
            tenant_id=TENANT, buyer_customer_id=customer.id, supplier_name="FinBrain",
            invoice_no="INV-100", total_amount=Decimal("950.00"), currency="MYR",
            status="validated", due_date=date.today() - timedelta(days=10),
        )
        db.add_all([endpoint, invoice, TenantOutreachPolicy(
            tenant_id=TENANT, telegram_reminders_enabled=True, grace_days=1,
            repeat_interval_days=7, max_reminders=3, require_approval=False,
        )])
        db.commit()

        first = plan_due_reminders(db, TENANT, date.today())
        second = plan_due_reminders(db, TENANT, date.today())

        assert first.created == 1
        assert second.created == 0
        action = db.query(OutreachAction).one()
        assert action.channel == "telegram"
        assert action.status == "approved"
        assert action.origin_invoice_id == invoice.id
        assert "INV-100" in action.protected_body
        assert "950.00" not in action.protected_body
    finally:
        db.close()


def test_paid_invoice_and_disabled_policy_create_no_reminder():
    db = _session()
    try:
        db.add(TenantOutreachPolicy(tenant_id=TENANT, telegram_reminders_enabled=False))
        db.commit()
        assert plan_due_reminders(db, TENANT, date.today()).created == 0
        assert db.query(OutreachAction).count() == 0
    finally:
        db.close()

