from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Customer,
    CustomerAttentionSignal,
    CustomerRecordLink,
    EInvoiceRecord,
    ProtectedTokenRegistry,
    TokenizedContent,
)
from app.schemas import (
    CustomerAttentionSignalResponse,
    CustomerDetailResponse,
    CustomerSummaryResponse,
    CustomerTimelineItemResponse,
)
from app.services.customer_attention import latest_attention


def _financials(db: Session, tenant_id: str, customer_id: int) -> tuple[Decimal, Decimal, int]:
    rows = db.scalars(
        select(EInvoiceRecord).where(
            EInvoiceRecord.tenant_id == tenant_id,
            EInvoiceRecord.buyer_customer_id == customer_id,
        )
    ).all()
    now = datetime.now(UTC).date()
    outstanding = [row for row in rows if row.status == "validated" and row.paid_at is None]
    overdue = [row for row in outstanding if row.due_date and row.due_date < now]
    return (
        sum((row.total_amount for row in outstanding), Decimal(0)),
        sum((row.total_amount for row in overdue), Decimal(0)),
        len(rows),
    )


def customer_summary(db: Session, tenant_id: str, customer: Customer) -> CustomerSummaryResponse:
    snapshot = latest_attention(db, tenant_id, customer.id)
    outstanding, overdue, invoice_count = _financials(db, tenant_id, customer.id)
    linked = db.scalar(
        select(func.count(func.distinct(CustomerRecordLink.tokenized_content_id))).where(
            CustomerRecordLink.tenant_id == tenant_id,
            CustomerRecordLink.customer_id == customer.id,
            CustomerRecordLink.match_status == "verified",
        )
    ) or 0
    registry = (
        db.get(ProtectedTokenRegistry, customer.primary_name_token)
        if customer.primary_name_token
        else None
    )
    return CustomerSummaryResponse(
        id=customer.id, name=registry.masked_value if registry else customer.canonical_name,
        profile_status=customer.profile_status,
        identity_review_status=customer.identity_review_status,
        profile_origin=customer.profile_origin,
        attention_score=snapshot.score if snapshot else 0,
        priority=snapshot.priority if snapshot else "healthy",
        outstanding_total=outstanding, overdue_total=overdue,
        invoice_count=invoice_count, linked_source_count=linked,
    )


def list_customers(db: Session, tenant_id: str) -> list[CustomerSummaryResponse]:
    customers = db.scalars(
        select(Customer).where(Customer.tenant_id == tenant_id).order_by(Customer.canonical_name)
    ).all()
    result = [customer_summary(db, tenant_id, customer) for customer in customers]
    return sorted(result, key=lambda row: (-row.attention_score, row.name.casefold()))


def customer_detail(db: Session, tenant_id: str, customer_id: int) -> CustomerDetailResponse:
    customer = db.get(Customer, customer_id)
    if customer is None or customer.tenant_id != tenant_id:
        raise LookupError("customer_not_found")
    summary = customer_summary(db, tenant_id, customer)
    snapshot = latest_attention(db, tenant_id, customer_id)
    signals = []
    if snapshot:
        signals = [
            CustomerAttentionSignalResponse.model_validate({
                "signal_type": row.signal_type, "points": row.points, "label": row.label,
                "freshness": row.freshness, "confidence": row.confidence,
                "tokenized_content_id": row.tokenized_content_id,
                "einvoice_record_id": row.einvoice_record_id,
            })
            for row in db.scalars(
                select(CustomerAttentionSignal)
                .where(CustomerAttentionSignal.snapshot_id == snapshot.id)
                .order_by(CustomerAttentionSignal.points.desc())
            ).all()
        ]
    timeline = [
        CustomerTimelineItemResponse(
            event_id=f"content:{row.id}", event_type="protected_record",
            source_system=row.source_system, occurred_at=row.occurred_at,
            protected_summary=row.summary or row.content_text[:500], tokenized_content_id=row.id,
            identity_status=link.match_status,
        )
        for link, row in db.execute(
            select(CustomerRecordLink, TokenizedContent)
            .join(TokenizedContent, TokenizedContent.id == CustomerRecordLink.tokenized_content_id)
            .where(
                CustomerRecordLink.tenant_id == tenant_id,
                CustomerRecordLink.customer_id == customer_id,
                CustomerRecordLink.match_status == "verified",
            )
        ).all()
    ]
    timeline.sort(
        key=lambda item: item.occurred_at or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )
    return CustomerDetailResponse(
        **summary.model_dump(),
        attention_version=snapshot.calculation_version if snapshot else None,
        attention_signals=signals,
        timeline=timeline,
    )
