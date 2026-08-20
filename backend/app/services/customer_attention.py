import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CustomerAttentionSignal,
    CustomerAttentionSnapshot,
    CustomerRecordLink,
    EInvoiceRecord,
    TokenizedContent,
)

CALCULATION_VERSION = "attention-v1"


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _freshness(value: datetime | None, now: datetime) -> tuple[str, float]:
    occurred = _aware(value)
    if occurred is None:
        return "undated", 1.0
    age = max(0, (now - occurred).days)
    if age <= 30:
        return "current", 1.0
    if age <= 90:
        return "aging", 1.0
    return "stale", 0.5


def _priority(score: int) -> str:
    if score >= 70:
        return "urgent"
    if score >= 40:
        return "high"
    if score >= 15:
        return "monitoring"
    return "healthy"


def recalculate_customer_attention(
    db: Session, tenant_id: str, customer_id: int
) -> CustomerAttentionSnapshot:
    now = datetime.now(UTC)
    invoices = db.scalars(
        select(EInvoiceRecord).where(
            EInvoiceRecord.tenant_id == tenant_id,
            EInvoiceRecord.buyer_customer_id == customer_id,
        )
    ).all()
    linked = db.execute(
        select(CustomerRecordLink, TokenizedContent)
        .join(TokenizedContent, TokenizedContent.id == CustomerRecordLink.tokenized_content_id)
        .where(
            CustomerRecordLink.tenant_id == tenant_id,
            CustomerRecordLink.customer_id == customer_id,
            CustomerRecordLink.match_status == "verified",
        )
    ).all()
    payload = {
        "version": CALCULATION_VERSION,
        "invoices": [
            (row.id, row.status, str(row.total_amount), str(row.due_date), str(row.paid_at))
            for row in invoices
        ],
        "records": [(link.id, row.id, row.updated_at.isoformat()) for link, row in linked],
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    existing = db.scalar(
        select(CustomerAttentionSnapshot).where(
            CustomerAttentionSnapshot.tenant_id == tenant_id,
            CustomerAttentionSnapshot.customer_id == customer_id,
            CustomerAttentionSnapshot.input_fingerprint == fingerprint,
        )
    )
    if existing:
        return existing

    signals: list[dict] = []
    overdue = [
        row for row in invoices
        if row.status == "validated" and row.paid_at is None and row.due_date
        and row.due_date < now.date()
    ]
    if overdue:
        oldest = max((now.date() - row.due_date).days for row in overdue)
        points = 10 if oldest <= 7 else 20 if oldest <= 30 else 30 if oldest <= 60 else 40
        evidence = min(overdue, key=lambda row: row.due_date)
        signals.append({
            "signal_type": "overdue_invoice", "points": points,
            "label": f"Oldest invoice is {oldest} days overdue", "freshness": "current",
            "confidence": 1.0, "einvoice_record_id": evidence.id,
            "occurred_at": None, "details": {"overdue_days": oldest},
        })
    outstanding = sum(
        (row.total_amount for row in invoices if row.status == "validated" and row.paid_at is None),
        Decimal(0),
    )
    if outstanding >= 1000 and invoices:
        points = 15 if outstanding >= 10000 else 10 if outstanding >= 5000 else 5
        evidence = max(invoices, key=lambda row: row.total_amount)
        signals.append({
            "signal_type": "outstanding_balance", "points": points,
            "label": "Customer has an outstanding validated balance", "freshness": "current",
            "confidence": 1.0, "einvoice_record_id": evidence.id,
            "occurred_at": None, "details": {"amount": str(outstanding)},
        })
    action_points = 0
    seen: set[int] = set()
    for _link, row in linked:
        if row.id in seen or not row.structured_summary:
            continue
        seen.add(row.id)
        summary = row.structured_summary
        if not summary.get("action_required"):
            continue
        base = 15 if summary.get("priority") == "high" else 8
        freshness, multiplier = _freshness(row.occurred_at, now)
        points = int(base * multiplier)
        if action_points + points > 30:
            points = max(0, 30 - action_points)
        if not points:
            continue
        action_points += points
        signals.append({
            "signal_type": "action_required_record", "points": points,
            "label": "A linked protected record requires action", "freshness": freshness,
            "confidence": 1.0, "tokenized_content_id": row.id,
            "occurred_at": row.occurred_at, "details": {"category": summary.get("category")},
        })
    score = min(100, sum(item["points"] for item in signals))
    snapshot = CustomerAttentionSnapshot(
        tenant_id=tenant_id, customer_id=customer_id, score=score,
        priority=_priority(score), calculation_version=CALCULATION_VERSION,
        input_fingerprint=fingerprint, calculated_at=now,
    )
    db.add(snapshot)
    db.flush()
    for item in signals:
        db.add(CustomerAttentionSignal(tenant_id=tenant_id, snapshot_id=snapshot.id, **item))
    db.commit()
    return snapshot


def latest_attention(
    db: Session, tenant_id: str, customer_id: int
) -> CustomerAttentionSnapshot | None:
    return db.scalar(
        select(CustomerAttentionSnapshot)
        .where(
            CustomerAttentionSnapshot.tenant_id == tenant_id,
            CustomerAttentionSnapshot.customer_id == customer_id,
        )
        .order_by(
            CustomerAttentionSnapshot.calculated_at.desc(),
            CustomerAttentionSnapshot.id.desc(),
        )
        .limit(1)
    )
