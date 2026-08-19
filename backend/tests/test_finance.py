from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, Customer, EInvoiceRecord
from app.schemas import UserRole
from app.services.einvoice_readiness import mark_invoice_paid
from app.services.finance import _period_bounds, revenue_summary
from app.services.workflow_audit import verify_workflow_chain
from tests.auth_support import TENANT_A, TENANT_B

TENANT_A_ID = str(TENANT_A)
TENANT_B_ID = str(TENANT_B)


def _database() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _invoice(
    *,
    tenant_id: str = TENANT_A_ID,
    total_amount: str = "1000.00",
    status: str = "validated",
    issue_date: date | None = None,
    due_date: date | None = None,
    paid_at: date | None = None,
    buyer_customer_id: int | None = None,
    supplier_name: str = "Acme Sdn Bhd",
) -> EInvoiceRecord:
    return EInvoiceRecord(
        tenant_id=tenant_id,
        supplier_name=supplier_name,
        total_amount=Decimal(total_amount),
        status=status,
        issue_date=issue_date,
        due_date=due_date,
        paid_at=paid_at,
        buyer_customer_id=buyer_customer_id,
    )


def test_period_bounds_month_current_and_prior():
    now = datetime(2026, 8, 19, 12, tzinfo=UTC)
    assert _period_bounds("month", 0, now=now, timezone_name="UTC") == (
        date(2026, 8, 1),
        date(2026, 9, 1),
    )
    assert _period_bounds("month", -1, now=now, timezone_name="UTC") == (
        date(2026, 7, 1),
        date(2026, 8, 1),
    )


def test_period_bounds_month_december_rollover():
    now = datetime(2026, 12, 15, tzinfo=UTC)
    assert _period_bounds("month", 0, now=now, timezone_name="UTC") == (
        date(2026, 12, 1),
        date(2027, 1, 1),
    )
    assert _period_bounds("month", 1, now=now, timezone_name="UTC") == (
        date(2027, 1, 1),
        date(2027, 2, 1),
    )


def test_period_bounds_quarter_current_and_year_rollover():
    now = datetime(2026, 8, 19, tzinfo=UTC)  # Q3 2026
    assert _period_bounds("quarter", 0, now=now, timezone_name="UTC") == (
        date(2026, 7, 1),
        date(2026, 10, 1),
    )
    # January is Q1 -- the prior quarter must roll back into the previous year.
    q1_now = datetime(2026, 1, 15, tzinfo=UTC)
    assert _period_bounds("quarter", -1, now=q1_now, timezone_name="UTC") == (
        date(2025, 10, 1),
        date(2026, 1, 1),
    )


def test_period_bounds_year():
    now = datetime(2026, 8, 19, tzinfo=UTC)
    assert _period_bounds("year", 0, now=now, timezone_name="UTC") == (
        date(2026, 1, 1),
        date(2027, 1, 1),
    )
    assert _period_bounds("year", -1, now=now, timezone_name="UTC") == (
        date(2025, 1, 1),
        date(2026, 1, 1),
    )


def test_revenue_summary_only_counts_validated_invoices_in_period():
    db = _database()
    try:
        now = datetime(2026, 8, 19, tzinfo=UTC)
        db.add_all(
            [
                _invoice(total_amount="1000.00", status="validated", issue_date=date(2026, 8, 5)),
                _invoice(total_amount="500.00", status="pending", issue_date=date(2026, 8, 6)),
                _invoice(total_amount="300.00", status="validated", issue_date=date(2026, 7, 15)),
            ]
        )
        db.commit()

        summary = revenue_summary(db, TENANT_A_ID, period="month", offset=0, now=now)

        assert summary.total_revenue == Decimal("1000.00")
        assert summary.prior_period_revenue == Decimal("300.00")
        assert summary.revenue_change_pct == pytest.approx((1000 - 300) / 300 * 100)
    finally:
        db.close()


def test_ar_aging_buckets_at_exact_boundaries():
    db = _database()
    try:
        now = datetime(2026, 8, 19, tzinfo=UTC)
        today = now.date()
        rows = [
            _invoice(total_amount="10.00", due_date=today - timedelta(days=30)),  # 1-30
            _invoice(total_amount="20.00", due_date=today - timedelta(days=31)),  # 31-60
            _invoice(total_amount="30.00", due_date=today - timedelta(days=60)),  # 31-60
            _invoice(total_amount="40.00", due_date=today - timedelta(days=61)),  # 61-90
            _invoice(total_amount="50.00", due_date=today - timedelta(days=90)),  # 61-90
            _invoice(total_amount="60.00", due_date=today - timedelta(days=91)),  # 90+
            _invoice(total_amount="70.00", due_date=today),  # current (due today)
            _invoice(total_amount="80.00", due_date=None),  # current (no due date)
        ]
        db.add_all(rows)
        db.commit()

        summary = revenue_summary(db, TENANT_A_ID, period="month", offset=0, now=now)

        buckets = {bucket.label: bucket for bucket in summary.ar_aging}
        assert buckets["1-30"].total_amount == Decimal("10.00")
        assert buckets["31-60"].total_amount == Decimal("50.00")
        assert buckets["61-90"].total_amount == Decimal("90.00")
        assert buckets["90+"].total_amount == Decimal("60.00")
        assert buckets["current"].total_amount == Decimal("150.00")
        assert summary.outstanding_ar == Decimal("360.00")
    finally:
        db.close()


def test_top_customers_ordered_by_revenue_descending():
    db = _database()
    try:
        big = Customer(
            tenant_id=TENANT_A_ID, canonical_name="Big Buyer", normalized_name="BIGBUYER"
        )
        small = Customer(
            tenant_id=TENANT_A_ID, canonical_name="Small Buyer", normalized_name="SMALLBUYER"
        )
        db.add_all([big, small])
        db.flush()
        db.add_all(
            [
                _invoice(total_amount="100.00", buyer_customer_id=small.id),
                _invoice(total_amount="900.00", buyer_customer_id=big.id),
                _invoice(total_amount="100.00", buyer_customer_id=big.id),
            ]
        )
        db.commit()

        summary = revenue_summary(db, TENANT_A_ID, period="year", offset=0)

        names = [c.name for c in summary.top_customers]
        assert names[0] == "Big Buyer"
        assert summary.top_customers[0].total_amount == Decimal("1000.00")
        assert summary.top_customers[0].invoice_count == 2
    finally:
        db.close()


def test_revenue_summary_is_tenant_isolated():
    db = _database()
    try:
        now = datetime(2026, 8, 19, tzinfo=UTC)
        db.add_all(
            [
                _invoice(
                    tenant_id=TENANT_A_ID, total_amount="1000.00", issue_date=date(2026, 3, 1)
                ),
                _invoice(
                    tenant_id=TENANT_B_ID, total_amount="9999.00", issue_date=date(2026, 3, 1)
                ),
            ]
        )
        db.commit()

        summary_a = revenue_summary(db, TENANT_A_ID, period="year", offset=0, now=now)
        summary_b = revenue_summary(db, TENANT_B_ID, period="year", offset=0, now=now)

        assert summary_a.total_revenue == Decimal("1000.00")
        assert summary_b.total_revenue == Decimal("9999.00")
    finally:
        db.close()


def test_mark_invoice_paid_sets_paid_at_and_writes_workflow_event():
    db = _database()
    try:
        record = _invoice(status="validated")
        db.add(record)
        db.commit()

        response = mark_invoice_paid(
            db,
            record.id,
            role=UserRole.FINANCE_OPS,
            actor_ref="test-actor",
            tenant_id=TENANT_A_ID,
            paid_at=date(2026, 8, 19),
        )

        assert response.paid_at == date(2026, 8, 19)
        assert verify_workflow_chain(db, TENANT_A_ID)
    finally:
        db.close()


def test_mark_invoice_paid_rejects_pending_or_already_paid():
    db = _database()
    try:
        pending = _invoice(status="pending")
        already_paid = _invoice(status="validated", paid_at=date(2026, 1, 1))
        db.add_all([pending, already_paid])
        db.commit()

        with pytest.raises(ValueError):
            mark_invoice_paid(
                db, pending.id, role=UserRole.FINANCE_OPS, actor_ref="t", tenant_id=TENANT_A_ID
            )
        with pytest.raises(ValueError):
            mark_invoice_paid(
                db,
                already_paid.id,
                role=UserRole.FINANCE_OPS,
                actor_ref="t",
                tenant_id=TENANT_A_ID,
            )
    finally:
        db.close()


def test_mark_invoice_paid_cross_tenant_raises_lookup_error():
    db = _database()
    try:
        record = _invoice(tenant_id=TENANT_A_ID, status="validated")
        db.add(record)
        db.commit()

        with pytest.raises(LookupError):
            mark_invoice_paid(
                db, record.id, role=UserRole.FINANCE_OPS, actor_ref="t", tenant_id=TENANT_B_ID
            )
    finally:
        db.close()
