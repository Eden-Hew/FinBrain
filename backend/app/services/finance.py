from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Customer, EInvoiceRecord
from app.schemas import (
    ARAgingBucket,
    FinanceSummaryResponse,
    InvoiceStatusBreakdown,
    RevenuePeriodPoint,
    TopCustomer,
)

Period = Literal["month", "quarter", "year"]

_AGING_LABELS: tuple[Literal["current", "1-30", "31-60", "61-90", "90+"], ...] = (
    "current",
    "1-30",
    "31-60",
    "61-90",
    "90+",
)


def _to_decimal(value: object) -> Decimal:
    """Convert a raw SQL aggregate result to Decimal via str(), avoiding the binary-
    float precision artifacts a direct Decimal(float) conversion can introduce."""
    if value is None:
        return Decimal(0)
    return Decimal(str(value))


def _period_bounds(
    period: Period,
    offset: int,
    *,
    now: datetime | None = None,
    timezone_name: str | None = None,
) -> tuple[date, date]:
    """Return (start, end) calendar dates for one period, offset periods back from
    the current one (offset=0 is the current period, offset=-1 the prior one).
    `end` is exclusive. EInvoiceRecord's date columns carry no time component, so
    this works entirely in calendar dates rather than timezone-aware instants --
    the timezone only decides what "today" is, matching query_planning.py's
    local-midnight anchoring pattern.
    """
    zone = ZoneInfo(timezone_name or get_settings().application_timezone)
    today = (now or datetime.now(UTC)).astimezone(zone).date()

    if period == "month":
        anchor = today.year * 12 + (today.month - 1) + offset
        start_year, start_month = divmod(anchor, 12)
        start = date(start_year, start_month + 1, 1)
        end_year, end_month = divmod(anchor + 1, 12)
        end = date(end_year, end_month + 1, 1)
    elif period == "quarter":
        anchor = today.year * 4 + (today.month - 1) // 3 + offset
        start_year, start_quarter = divmod(anchor, 4)
        start = date(start_year, start_quarter * 3 + 1, 1)
        end_year, end_quarter = divmod(anchor + 1, 4)
        end = date(end_year, end_quarter * 3 + 1, 1)
    else:
        start = date(today.year + offset, 1, 1)
        end = date(today.year + offset + 1, 1, 1)

    return start, end


def _revenue_between(db: Session, tenant_id: str, start: date, end: date) -> Decimal:
    total = db.scalar(
        select(func.sum(EInvoiceRecord.total_amount)).where(
            EInvoiceRecord.tenant_id == tenant_id,
            EInvoiceRecord.status == "validated",
            EInvoiceRecord.issue_date >= start,
            EInvoiceRecord.issue_date < end,
        )
    )
    return _to_decimal(total)


def _aging_buckets(rows: list[EInvoiceRecord], *, as_of: date | None = None) -> list[ARAgingBucket]:
    as_of = as_of or datetime.now(UTC).date()
    buckets: dict[str, list[EInvoiceRecord]] = {label: [] for label in _AGING_LABELS}
    for row in rows:
        if row.due_date is None or row.due_date >= as_of:
            buckets["current"].append(row)
            continue
        days_overdue = (as_of - row.due_date).days
        if days_overdue <= 30:
            buckets["1-30"].append(row)
        elif days_overdue <= 60:
            buckets["31-60"].append(row)
        elif days_overdue <= 90:
            buckets["61-90"].append(row)
        else:
            buckets["90+"].append(row)
    return [
        ARAgingBucket(
            label=label,
            count=len(items),
            total_amount=sum((item.total_amount for item in items), Decimal(0)),
        )
        for label, items in buckets.items()
    ]


def _revenue_trend(
    db: Session,
    tenant_id: str,
    *,
    months: int,
    timezone_name: str | None,
    now: datetime | None = None,
) -> list[RevenuePeriodPoint]:
    points = []
    for offset in range(-(months - 1), 1):
        start, end = _period_bounds("month", offset, now=now, timezone_name=timezone_name)
        points.append(
            RevenuePeriodPoint(
                period_label=start.strftime("%b %Y"),
                period_start=start,
                total_amount=_revenue_between(db, tenant_id, start, end),
            )
        )
    return points


def _top_customers(db: Session, tenant_id: str, *, limit: int) -> list[TopCustomer]:
    rows = db.execute(
        select(
            Customer.id,
            Customer.canonical_name,
            func.sum(EInvoiceRecord.total_amount),
            func.count(EInvoiceRecord.id),
        )
        .join(EInvoiceRecord, EInvoiceRecord.buyer_customer_id == Customer.id)
        .where(EInvoiceRecord.tenant_id == tenant_id, EInvoiceRecord.status == "validated")
        .group_by(Customer.id, Customer.canonical_name)
        .order_by(func.sum(EInvoiceRecord.total_amount).desc())
        .limit(limit)
    ).all()
    return [
        TopCustomer(
            customer_id=row[0], name=row[1], total_amount=_to_decimal(row[2]), invoice_count=row[3]
        )
        for row in rows
    ]


def _status_bucket(
    db: Session, tenant_id: str, *, validated: bool, paid: bool | None = None
) -> tuple[int, Decimal]:
    # "pending" here means "not yet validated" -- a catch-all for anything short of
    # a validated invoice, not the literal string "pending". Demo seed data also uses
    # "review"/"submitted" as decorative pre-validation statuses that no real code
    # path (create_record/approve_record) ever produces; a strict `== "pending"`
    # match would silently drop those rows from every bucket instead of counting
    # them as still-pending, understating totals for no real reason.
    conditions = [
        EInvoiceRecord.tenant_id == tenant_id,
        EInvoiceRecord.status == "validated" if validated else EInvoiceRecord.status != "validated",
    ]
    if paid is True:
        conditions.append(EInvoiceRecord.paid_at.is_not(None))
    elif paid is False:
        conditions.append(EInvoiceRecord.paid_at.is_(None))
    count, total = db.execute(
        select(func.count(), func.sum(EInvoiceRecord.total_amount)).where(*conditions)
    ).one()
    return int(count or 0), _to_decimal(total)


def _status_breakdown(db: Session, tenant_id: str) -> list[InvoiceStatusBreakdown]:
    pending_count, pending_total = _status_bucket(db, tenant_id, validated=False)
    outstanding_count, outstanding_total = _status_bucket(db, tenant_id, validated=True, paid=False)
    paid_count, paid_total = _status_bucket(db, tenant_id, validated=True, paid=True)
    return [
        InvoiceStatusBreakdown(label="pending", count=pending_count, total_amount=pending_total),
        InvoiceStatusBreakdown(
            label="outstanding", count=outstanding_count, total_amount=outstanding_total
        ),
        InvoiceStatusBreakdown(label="paid", count=paid_count, total_amount=paid_total),
    ]


def revenue_summary(
    db: Session,
    tenant_id: str,
    *,
    period: Period,
    offset: int = 0,
    timezone_name: str | None = None,
    top_customer_limit: int = 5,
    trend_months: int = 12,
    now: datetime | None = None,
) -> FinanceSummaryResponse:
    start, end = _period_bounds(period, offset, now=now, timezone_name=timezone_name)
    prior_start, prior_end = _period_bounds(
        period, offset - 1, now=now, timezone_name=timezone_name
    )

    total_revenue = _revenue_between(db, tenant_id, start, end)
    prior_period_revenue = _revenue_between(db, tenant_id, prior_start, prior_end)
    revenue_change_pct = (
        float((total_revenue - prior_period_revenue) / prior_period_revenue * 100)
        if prior_period_revenue
        else None
    )

    outstanding_rows = list(
        db.scalars(
            select(EInvoiceRecord).where(
                EInvoiceRecord.tenant_id == tenant_id,
                EInvoiceRecord.status == "validated",
                EInvoiceRecord.paid_at.is_(None),
            )
        ).all()
    )
    outstanding_ar = sum((row.total_amount for row in outstanding_rows), Decimal(0))

    paid_rows = list(
        db.scalars(
            select(EInvoiceRecord).where(
                EInvoiceRecord.tenant_id == tenant_id,
                EInvoiceRecord.paid_at.is_not(None),
                EInvoiceRecord.issue_date.is_not(None),
            )
        ).all()
    )
    avg_days_to_pay = (
        sum((row.paid_at - row.issue_date).days for row in paid_rows) / len(paid_rows)
        if paid_rows
        else None
    )

    validated_invoice_count = int(
        db.scalar(
            select(func.count()).where(
                EInvoiceRecord.tenant_id == tenant_id, EInvoiceRecord.status == "validated"
            )
        )
        or 0
    )

    return FinanceSummaryResponse(
        period=period,
        period_start=start,
        period_end=end,
        total_revenue=total_revenue,
        prior_period_revenue=prior_period_revenue,
        revenue_change_pct=revenue_change_pct,
        outstanding_ar=outstanding_ar,
        ar_aging=_aging_buckets(outstanding_rows, as_of=now.date() if now else None),
        revenue_trend=_revenue_trend(
            db, tenant_id, months=trend_months, timezone_name=timezone_name, now=now
        ),
        top_customers=_top_customers(db, tenant_id, limit=top_customer_limit),
        status_breakdown=_status_breakdown(db, tenant_id),
        validated_invoice_count=validated_invoice_count,
        avg_days_to_pay=avg_days_to_pay,
    )
