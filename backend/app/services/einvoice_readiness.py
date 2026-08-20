import secrets
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import EinvoiceOutreachDraft, EInvoiceRecord
from app.schemas import (
    CanonicalIngestionRecord,
    EInvoiceCreatePayload,
    EinvoiceDocumentUrlResponse,
    EinvoiceOutreachDraftResponse,
    EinvoiceReadinessCategory,
    EinvoiceReadinessResponse,
    EInvoiceRecordResponse,
    UserRole,
)
from app.services import storage
from app.services.einvoice_pdf import render_einvoice_pdf
from app.services.entity_resolution import (
    normalize_business_name,
    register_structured_customer_aliases,
    resolve_customer,
)
from app.services.ingestion import ingest_canonical_record
from app.services.workflow_audit import write_workflow_event

_DECISION_TRANSITIONS = {
    "approved": "draft",
    "rejected": "draft",
}


def record_response(
    row: EInvoiceRecord, reason: str = "All required fields present."
) -> EInvoiceRecordResponse:
    return EInvoiceRecordResponse(
        id=row.id,
        supplier_name=row.supplier_name,
        supplier_tin=row.supplier_tin,
        buyer_name=row.buyer_name,
        buyer_customer_id=row.buyer_customer_id,
        invoice_no=row.invoice_no,
        issue_date=row.issue_date,
        due_date=row.due_date,
        currency=row.currency,
        tax_type=row.tax_type,
        tax_rate=row.tax_rate,
        total_amount=row.total_amount,
        status=row.status,
        paid_at=row.paid_at,
        created_at=row.created_at,
        document_available=True,
        readiness_reason=reason,
        uin=row.uin,
    )


def list_records(db: Session, tenant_id: str) -> list[EInvoiceRecordResponse]:
    rows = db.scalars(
        select(EInvoiceRecord)
        .where(EInvoiceRecord.tenant_id == tenant_id)
        .order_by(EInvoiceRecord.issue_date.desc(), EInvoiceRecord.created_at.desc())
    ).all()
    return [record_response(r) for r in rows]


def _canonical_einvoice_text(record: EInvoiceRecord) -> str:
    tax = f"{record.tax_type or 'unspecified'} {record.tax_rate or ''}".strip()
    lines = [
        f"Invoice: {record.invoice_no or 'unassigned'}",
        f"Supplier: {record.supplier_name}",
        f"Supplier TIN: {record.supplier_tin or 'missing'}",
        f"Buyer: {record.buyer_name or 'unknown'}",
        f"Issue date: {record.issue_date.isoformat() if record.issue_date else 'unknown'}",
        f"Amount: {record.currency or 'MYR'} {record.total_amount}",
        f"Tax: {tax}",
        f"Status: {record.status}",
        f"UIN: {record.uin or 'not yet issued'}",
    ]
    return "\n".join(lines)


def sync_einvoice_tokenized_content(db: Session, record: EInvoiceRecord) -> None:
    """Mirror this operational e-invoice row into the protected/tokenized pipeline so
    Customer Intelligence chat can retrieve and cite it, just like every other source.
    The plain-column table stays the operational store for Readiness Check / All invoices
    — this only feeds the searchable, PII-protected copy chat reads from."""
    occurred_at = (
        datetime.combine(record.issue_date, datetime.min.time(), tzinfo=UTC)
        if record.issue_date
        else None
    )
    canonical = CanonicalIngestionRecord(
        source_record_id=f"einvoice:{record.id}",
        source_system="einvoice",
        record_type="einvoice",
        text=_canonical_einvoice_text(record),
        occurred_at=occurred_at,
        tenant_id=record.tenant_id,
        metadata={
            "status": record.status,
            "has_tin": str(bool(record.supplier_tin)).lower(),
            "currency": record.currency or "MYR",
        },
    )
    result = ingest_canonical_record(db, canonical)
    record.source_record_id = result.source_record_id
    db.commit()


def sync_all_einvoice_tokenized_content(db: Session) -> int:
    """Idempotently mirror every operational e-invoice into protected search."""
    records = db.scalars(select(EInvoiceRecord).order_by(EInvoiceRecord.id)).all()
    for record in records:
        sync_einvoice_tokenized_content(db, record)
    return len(records)


def create_record(
    db: Session, payload: EInvoiceCreatePayload, *, role: UserRole, actor_ref: str, tenant_id: str
) -> EInvoiceRecordResponse:
    buyer_customer = (
        resolve_customer(db, tenant_id, payload.buyer_name) if payload.buyer_name else None
    )
    due_date = payload.due_date
    if due_date is None and payload.issue_date is not None:
        terms = get_settings().default_payment_terms_days
        due_date = payload.issue_date + timedelta(days=terms)
    record = EInvoiceRecord(
        tenant_id=tenant_id,
        supplier_name=payload.supplier_name,
        supplier_tin=payload.supplier_tin,
        buyer_name=payload.buyer_name,
        buyer_customer_id=buyer_customer.id if buyer_customer else None,
        invoice_no=payload.invoice_no,
        issue_date=payload.issue_date,
        due_date=due_date,
        currency=payload.currency,
        tax_type=payload.tax_type,
        tax_rate=payload.tax_rate,
        total_amount=payload.total_amount,
        status="pending",
    )
    db.add(record)
    db.flush()
    if buyer_customer and payload.buyer_name:
        register_structured_customer_aliases(
            db,
            buyer_customer,
            payload.buyer_name,
            source_system="einvoice",
            source_record_id=f"einvoice:{record.id}",
        )

    write_workflow_event(
        db,
        event_type="einvoice_record_created",
        actor_role=role.value,
        actor_ref=actor_ref,
        resource_type="einvoice_record",
        resource_id=str(record.id),
        tenant_id=tenant_id,
        event_payload={
            "supplier_name": record.supplier_name,
            "total_amount": str(record.total_amount),
        },
    )
    db.commit()
    sync_einvoice_tokenized_content(db, record)
    return record_response(record)


def get_record(db: Session, record_id: int, tenant_id: str) -> EInvoiceRecordResponse:
    record = db.get(EInvoiceRecord, record_id)
    if record is None or record.tenant_id != tenant_id:
        raise LookupError(f"e-invoice record {record_id} not found")
    return record_response(record)


def upload_record_document(
    db: Session, record_id: int, data: bytes, *, role: UserRole, actor_ref: str, tenant_id: str
) -> EInvoiceRecordResponse:
    record = db.get(EInvoiceRecord, record_id)
    if record is None or record.tenant_id != tenant_id:
        raise LookupError(f"e-invoice record {record_id} not found")

    bucket = get_settings().einvoice_document_bucket
    storage.ensure_bucket(bucket)
    path = f"{record.id}.pdf"
    storage.upload_bytes(bucket, path, data, content_type="application/pdf")
    record.document_storage_path = path
    db.flush()

    write_workflow_event(
        db,
        event_type="einvoice_document_uploaded",
        actor_role=role.value,
        actor_ref=actor_ref,
        resource_type="einvoice_record",
        resource_id=str(record.id),
        tenant_id=tenant_id,
        event_payload={"bytes": len(data)},
    )
    db.commit()
    return record_response(record)


def _generate_uin() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "MY29A" + "".join(secrets.choice(alphabet) for _ in range(6))


def approve_record(
    db: Session, record_id: int, *, role: UserRole, actor_ref: str, tenant_id: str
) -> EInvoiceRecordResponse:
    if role is not UserRole.OWNER_DIRECTOR:
        raise PermissionError("Owner/director role required")

    record = db.get(EInvoiceRecord, record_id)
    if record is None or record.tenant_id != tenant_id:
        raise LookupError(f"e-invoice record {record_id} not found")
    if record.status != "pending":
        raise ValueError(f"cannot approve an invoice in status '{record.status}'")

    previous_status = record.status
    record.uin = _generate_uin()
    record.status = "validated"
    db.flush()

    write_workflow_event(
        db,
        event_type="einvoice_submitted",
        actor_role=role.value,
        actor_ref=actor_ref,
        resource_type="einvoice_record",
        resource_id=str(record.id),
        tenant_id=tenant_id,
        event_payload={"uin": record.uin, "previous_status": previous_status},
    )
    db.commit()
    sync_einvoice_tokenized_content(db, record)
    return record_response(record)


def mark_invoice_paid(
    db: Session,
    record_id: int,
    *,
    role: UserRole,
    actor_ref: str,
    tenant_id: str,
    paid_at: date | None = None,
) -> EInvoiceRecordResponse:
    """Record payment against a validated invoice, orthogonal to `status` (document
    status). Required for outstanding AR to mean anything at all -- previously
    nothing distinguished a paid invoice from an unpaid one."""
    record = db.get(EInvoiceRecord, record_id)
    if record is None or record.tenant_id != tenant_id:
        raise LookupError(f"e-invoice record {record_id} not found")
    if record.status != "validated":
        raise ValueError(f"cannot mark an invoice paid in status '{record.status}'")
    if record.paid_at is not None:
        raise ValueError("invoice is already marked paid")

    record.paid_at = paid_at or datetime.now(UTC).date()
    db.flush()

    write_workflow_event(
        db,
        event_type="einvoice_payment_recorded",
        actor_role=role.value,
        actor_ref=actor_ref,
        resource_type="einvoice_record",
        resource_id=str(record.id),
        tenant_id=tenant_id,
        event_payload={"paid_at": record.paid_at.isoformat()},
    )
    db.commit()
    return record_response(record)


def _classify(row: EInvoiceRecord, name_groups: dict[str, set[str]]) -> tuple[str, str]:
    """Return (category, human-readable reason) for one record."""
    issues: list[str] = []

    if not row.supplier_tin:
        issues.append(
            "Missing supplier Tax Identification Number (TIN) — MyInvois will reject this "
            "invoice for submission without it."
        )

    variants = name_groups[normalize_business_name(row.supplier_name)]
    if len(variants) > 1:
        others = sorted(v for v in variants if v != row.supplier_name)
        issues.append(
            f"Supplier name is recorded inconsistently across invoices (also seen as "
            f"{', '.join(f'“{v}”' for v in others)}) — this can create duplicate or "
            "mismatched supplier records in MyInvois."
        )
    if not row.buyer_name:
        issues.append("Missing buyer name — required for a complete tax invoice.")
    if not row.tax_type:
        issues.append("Missing tax type — required to calculate the correct tax treatment.")

    if not row.supplier_tin:
        category = "critical"
    elif issues:
        category = "warning"
    else:
        category = "passing"

    reason = " ".join(issues) if issues else "All required fields present."
    return category, reason


def compute_readiness(
    db: Session,
    *,
    role: UserRole,
    actor_ref: str,
    tenant_id: str,
) -> EinvoiceReadinessResponse:
    rows = db.scalars(
        select(EInvoiceRecord)
        .where(EInvoiceRecord.tenant_id == tenant_id)
        .order_by(EInvoiceRecord.created_at.desc())
    ).all()

    name_groups: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        name_groups[normalize_business_name(row.supplier_name)].add(row.supplier_name)

    critical: list[EInvoiceRecordResponse] = []
    warning: list[EInvoiceRecordResponse] = []
    passing: list[EInvoiceRecordResponse] = []

    for row in rows:
        category, reason = _classify(row, name_groups)
        bucket = {"critical": critical, "warning": warning, "passing": passing}[category]
        bucket.append(record_response(row, reason))

    total = len(rows)
    score = round(len(passing) / total, 4) if total else 1.0

    result = EinvoiceReadinessResponse(
        score=score,
        total_records=total,
        passing_count=len(passing),
        critical=EinvoiceReadinessCategory(label="critical", count=len(critical), records=critical),
        warning=EinvoiceReadinessCategory(label="warning", count=len(warning), records=warning),
        passing=EinvoiceReadinessCategory(label="passing", count=len(passing), records=passing),
    )

    write_workflow_event(
        db,
        event_type="einvoice_readiness_computed",
        actor_role=role.value,
        actor_ref=actor_ref,
        resource_type="einvoice_readiness",
        resource_id="workspace",
        tenant_id=tenant_id,
        event_payload={
            "score": score,
            "total_records": total,
            "critical": len(critical),
            "warning": len(warning),
            "passing": len(passing),
        },
    )
    db.commit()
    return result


def _draft_response(row: EinvoiceOutreachDraft) -> EinvoiceOutreachDraftResponse:
    return EinvoiceOutreachDraftResponse(
        id=row.id,
        einvoice_record_id=row.einvoice_record_id,
        channel=row.channel,
        draft_text=row.draft_text,
        status=row.status,
        created_at=row.created_at,
        decided_at=row.decided_at,
    )


def _build_draft_text(record: EInvoiceRecord) -> str:
    return (
        f"Hi {record.supplier_name}, we're missing your Tax Identification Number (TIN) "
        f"for invoice {record.invoice_no or 'on file'} (RM {record.total_amount}). "
        "Could you share it so we can complete MyInvois submission?"
    )


def create_outreach_draft(
    db: Session,
    record_id: int,
    *,
    channel: str,
    role: UserRole,
    actor_ref: str,
    tenant_id: str,
    created_by_user_id: str | None,
) -> EinvoiceOutreachDraftResponse:
    record = db.get(EInvoiceRecord, record_id)
    if record is None or record.tenant_id != tenant_id:
        raise LookupError(f"e-invoice record {record_id} not found")

    draft = EinvoiceOutreachDraft(
        tenant_id=tenant_id,
        einvoice_record_id=record.id,
        channel=channel,
        draft_text=_build_draft_text(record),
        status="draft",
        created_by_user_id=created_by_user_id,
    )
    db.add(draft)
    db.flush()

    write_workflow_event(
        db,
        event_type="einvoice_outreach_drafted",
        actor_role=role.value,
        actor_ref=actor_ref,
        resource_type="einvoice_outreach_draft",
        resource_id=str(draft.id),
        tenant_id=tenant_id,
        event_payload={
            "einvoice_record_id": record.id,
            "channel": channel,
        },
    )
    db.commit()
    return _draft_response(draft)


def get_document_url(db: Session, record_id: int, tenant_id: str) -> EinvoiceDocumentUrlResponse:
    record = db.get(EInvoiceRecord, record_id)
    if record is None or record.tenant_id != tenant_id:
        raise LookupError(f"e-invoice record {record_id} not found")

    bucket = get_settings().einvoice_document_bucket
    expires_in = 300

    try:
        storage.ensure_bucket(bucket)
        if not record.document_storage_path:
            pdf_bytes = render_einvoice_pdf(record)
            path = f"{record.id}.pdf"
            storage.upload_bytes(bucket, path, pdf_bytes, content_type="application/pdf")
            record.document_storage_path = path
            db.commit()
        url = storage.create_signed_url(bucket, record.document_storage_path, expires_in=expires_in)
        return EinvoiceDocumentUrlResponse(url=url, expires_in=expires_in)
    except Exception:
        return EinvoiceDocumentUrlResponse(
            url=f"/einvoice-records/{record_id}/pdf", expires_in=expires_in
        )


def list_outreach_drafts(db: Session, tenant_id: str) -> list[EinvoiceOutreachDraftResponse]:
    rows = db.scalars(
        select(EinvoiceOutreachDraft)
        .where(
            EinvoiceOutreachDraft.status == "draft",
            EinvoiceOutreachDraft.tenant_id == tenant_id,
        )
        .order_by(EinvoiceOutreachDraft.created_at.desc())
    ).all()
    return [_draft_response(row) for row in rows]


def decide_outreach(
    db: Session,
    draft_id: int,
    *,
    decision: str,
    role: UserRole,
    actor_ref: str,
    tenant_id: str,
) -> EinvoiceOutreachDraftResponse:
    if role is not UserRole.OWNER_DIRECTOR:
        raise PermissionError("Owner/director role required")

    draft = db.get(EinvoiceOutreachDraft, draft_id)
    if draft is None or draft.tenant_id != tenant_id:
        raise LookupError(f"outreach draft {draft_id} not found")

    required_status = _DECISION_TRANSITIONS.get(decision)
    if required_status is None or draft.status != required_status:
        raise ValueError(f"cannot move draft from '{draft.status}' via '{decision}'")

    draft.status = decision
    draft.decided_at = datetime.now(UTC)
    db.flush()

    write_workflow_event(
        db,
        event_type=f"einvoice_outreach_{decision}",
        actor_role=role.value,
        actor_ref=actor_ref,
        resource_type="einvoice_outreach_draft",
        resource_id=str(draft.id),
        tenant_id=tenant_id,
        event_payload={
            "einvoice_record_id": draft.einvoice_record_id,
            "channel": draft.channel,
        },
    )
    db.commit()
    return _draft_response(draft)
