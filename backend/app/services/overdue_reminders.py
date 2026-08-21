import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Customer,
    CustomerEndpoint,
    EInvoiceRecord,
    OutreachAction,
    TenantOutreachPolicy,
)
from app.security.tokenize import protect_scalar
from app.services.workflow_audit import write_workflow_event


@dataclass(frozen=True, slots=True)
class ReminderPlanResult:
    eligible: int = 0
    created: int = 0
    skipped: int = 0


def _idempotency_key(
    tenant_id: str, invoice_id: int, endpoint_id: int, stage: int, policy_version: int
) -> str:
    payload = f"{tenant_id}|{invoice_id}|{endpoint_id}|{stage}|{policy_version}"
    return hashlib.sha256(payload.encode()).hexdigest()


def plan_due_reminders(
    db: Session, tenant_id: str, as_of: date
) -> ReminderPlanResult:
    policy = db.get(TenantOutreachPolicy, tenant_id)
    if policy is None or not policy.telegram_reminders_enabled:
        return ReminderPlanResult()
    invoices = db.scalars(select(EInvoiceRecord).where(
        EInvoiceRecord.tenant_id == tenant_id,
        EInvoiceRecord.status == "validated",
        EInvoiceRecord.paid_at.is_(None),
        EInvoiceRecord.due_date.is_not(None),
        EInvoiceRecord.due_date < as_of,
        EInvoiceRecord.buyer_customer_id.is_not(None),
    )).all()
    eligible = created = skipped = 0
    for invoice in invoices:
        overdue_days = (as_of - invoice.due_date).days
        if overdue_days <= policy.grace_days:
            skipped += 1
            continue
        customer = db.get(Customer, invoice.buyer_customer_id)
        if (
            customer is None
            or customer.profile_status != "confirmed"
            or customer.identity_review_status != "clear"
        ):
            skipped += 1
            continue
        endpoint = db.scalar(select(CustomerEndpoint).where(
            CustomerEndpoint.tenant_id == tenant_id,
            CustomerEndpoint.customer_id == customer.id,
            CustomerEndpoint.channel == "telegram",
            CustomerEndpoint.verification_status == "verified",
            CustomerEndpoint.delivery_token.is_not(None),
        ).order_by(CustomerEndpoint.id))
        if endpoint is None:
            skipped += 1
            continue
        eligible += 1
        stage = 1 + max(0, overdue_days - policy.grace_days - 1) // policy.repeat_interval_days
        if stage > policy.max_reminders:
            skipped += 1
            continue
        key = _idempotency_key(
            tenant_id, invoice.id, endpoint.id, stage, policy.policy_version
        )
        existing = db.scalar(select(OutreachAction).where(
            OutreachAction.tenant_id == tenant_id,
            OutreachAction.idempotency_key == key,
        ))
        if existing is not None:
            skipped += 1
            continue
        action_id = str(uuid.uuid4())
        amount = f"{invoice.currency or 'MYR'} {invoice.total_amount:.2f}"
        amount_token = protect_scalar(
            db,
            entity_type="AMOUNT",
            value=amount,
            source_record_id=f"outreach-body:{action_id}",
            tenant_id=tenant_id,
        )
        protected_body = (
            f"Payment reminder: Invoice {invoice.invoice_no or invoice.id} is overdue. "
            f"The outstanding amount is {amount_token}. Please arrange payment or contact us "
            "if you need assistance."
        )
        status = "pending_approval" if policy.require_approval else "approved"
        now = datetime.now(UTC)
        action = OutreachAction(
            id=action_id,
            tenant_id=tenant_id,
            customer_id=customer.id,
            customer_endpoint_id=endpoint.id,
            channel="telegram",
            protected_subject="Payment reminder",
            protected_body=protected_body,
            status=status,
            idempotency_key=key,
            created_by_actor_ref="overdue-reminders-worker",
            origin_type="overdue_invoice",
            origin_invoice_id=invoice.id,
            scheduled_for=now,
            approved_at=now if status == "approved" else None,
        )
        db.add(action)
        db.flush()
        write_workflow_event(
            db,
            event_type="overdue_reminder_planned",
            actor_role="system_worker",
            actor_ref="overdue-reminders-worker",
            resource_type="outreach_action",
            resource_id=action.id,
            tenant_id=tenant_id,
            event_payload={
                "invoice_id": invoice.id,
                "customer_id": customer.id,
                "channel": "telegram",
                "stage": stage,
                "status": status,
            },
        )
        db.commit()
        created += 1
    return ReminderPlanResult(eligible=eligible, created=created, skipped=skipped)
