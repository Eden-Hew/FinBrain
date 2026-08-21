"""Readiness report and idempotent, non-destructive demo-session preparation.

The default command is read-only.  ``--apply`` adds only deterministic,
seed-owned fixtures and never truncates operational data.  Telegram delivery
identities and Auth users are deliberately not fabricated.
"""

from __future__ import annotations

import argparse
import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from app.db import (
    SessionLocal,
    initialize_local_schema,
    set_rls_context,
    set_worker_context,
)
from app.integrations.structured_csv.service import ingest_structured_csv
from app.integrations.telegram.onboarding import (
    accept_consent,
    begin_onboarding,
    ingest_customer_message,
    submit_gmail,
    submit_name,
    submit_phone,
)
from app.models import (
    DEFAULT_TENANT_ID,
    AuthUserRole,
    Conversation,
    ConversationTurn,
    ConversationTurnCitation,
    Customer,
    CustomerEndpoint,
    CustomerRecordLink,
    EinvoiceOutreachDraft,
    EInvoiceRecord,
    EmailIngestionReceipt,
    EmailReplyCorrelation,
    OutreachAction,
    OutreachEvidence,
    ProcessRecommendation,
    RecommendationDecision,
    RecommendationEvidence,
    StructuredIngestionBatch,
    TelegramOnboardingSession,
    TenantOutreachPolicy,
    TokenizedContent,
)
from app.schemas import UserRole
from app.services.einvoice_readiness import sync_einvoice_tokenized_content
from app.services.outreach import create_action, transition_action, verify_endpoint
from app.services.overdue_reminders import plan_due_reminders
from app.services.workflow_audit import write_workflow_event
from scripts.seed_demo_customer import CUSTOMER_EMAIL
from scripts.seed_demo_customer import main as seed_demo_customer
from seed.seed_data import run as seed_base_data

SEED_ACTOR = "demo-session-seed-v1"
SEED_CONVERSATION_ID = "demo-session-customer-intelligence-v1"
SEED_TELEGRAM_INVOICE = "DEMO-TG-OVERDUE-9001"
SEED_EMAIL_ACTION_KEY = "demo-session:email:pending-approval:v1"
SEED_EMAIL_DRAFT_KEY = "demo-session:email:draft:v1"
SEED_SENT_ACTION_KEY = "demo-session:email:sent:v1"
SEED_REPLIED_ACTION_KEY = "demo-session:email:replied:v1"
CSV_PATH = Path(__file__).resolve().parents[2] / "demo" / "chat_upload_invoice_register.csv"
PLACEHOLDER_TELEGRAM_ID = 999_000_000_001


@dataclass(frozen=True, slots=True)
class Check:
    feature: str
    ready: bool
    observed: str
    requirement: str


def _count(db, model, *criteria) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(*criteria)) or 0)


def _owner_id(db) -> str | None:
    return db.scalar(
        select(AuthUserRole.user_id)
        .where(
            AuthUserRole.tenant_id == DEFAULT_TENANT_ID,
            AuthUserRole.user_role == UserRole.OWNER_DIRECTOR.value,
            AuthUserRole.active.is_(True),
        )
        .limit(1)
    )


def _finance_id(db) -> str | None:
    return db.scalar(
        select(AuthUserRole.user_id)
        .where(
            AuthUserRole.tenant_id == DEFAULT_TENANT_ID,
            AuthUserRole.user_role == UserRole.FINANCE_OPS.value,
            AuthUserRole.active.is_(True),
        )
        .limit(1)
    )


def collect_readiness(db, *, active_roles: set[str] | None = None) -> list[Check]:
    """Return feature-oriented coverage without detokenizing protected values."""
    roles = active_roles or set()
    required_roles = {role.value for role in UserRole}
    sources = set(
        db.scalars(
            select(TokenizedContent.source_system).where(
                TokenizedContent.tenant_id == DEFAULT_TENANT_ID,
                TokenizedContent.processing_status == "ready",
            )
        ).all()
    )
    verified_channels = set(
        db.scalars(
            select(CustomerEndpoint.channel).where(
                CustomerEndpoint.tenant_id == DEFAULT_TENANT_ID,
                CustomerEndpoint.verification_status == "verified",
            )
        ).all()
    )
    outreach_states = set(
        db.scalars(
            select(OutreachAction.status).where(OutreachAction.tenant_id == DEFAULT_TENANT_ID)
        ).all()
    )
    invoice_states = set(
        db.scalars(
            select(EInvoiceRecord.status).where(EInvoiceRecord.tenant_id == DEFAULT_TENANT_ID)
        ).all()
    )
    recommendation_states = set(
        db.scalars(
            select(ProcessRecommendation.status).where(
                ProcessRecommendation.tenant_id == DEFAULT_TENANT_ID
            )
        ).all()
    )
    telegram_completed = _count(
        db,
        TelegramOnboardingSession,
        TelegramOnboardingSession.tenant_id == DEFAULT_TENANT_ID,
        TelegramOnboardingSession.status == "completed",
    )
    policy = db.get(TenantOutreachPolicy, DEFAULT_TENANT_ID)
    overdue_reminders = _count(
        db,
        OutreachAction,
        OutreachAction.tenant_id == DEFAULT_TENANT_ID,
        OutreachAction.origin_type == "overdue_invoice",
    )
    return [
        Check(
            "tenant and role authorization",
            required_roles <= roles,
            f"roles={sorted(roles)}",
            f"active roles={sorted(required_roles)}",
        ),
        Check(
            "protected cross-source search",
            len(sources) >= 6,
            f"ready sources={sorted(sources)}",
            "at least six source systems",
        ),
        Check(
            "customer profiles and record links",
            _count(db, Customer, Customer.tenant_id == DEFAULT_TENANT_ID) >= 2
            and _count(
                db,
                CustomerRecordLink,
                CustomerRecordLink.tenant_id == DEFAULT_TENANT_ID,
                CustomerRecordLink.match_status == "verified",
            )
            >= 2,
            "customer and verified-link coverage",
            "two linked customer profiles",
        ),
        Check(
            "verified outbound endpoints",
            {"email", "telegram"} <= verified_channels,
            f"verified channels={sorted(verified_channels)}",
            "verified email and Telegram",
        ),
        Check(
            "completed Telegram onboarding",
            telegram_completed > 0,
            f"completed sessions={telegram_completed}",
            "one completed onboarding fixture or real session",
        ),
        Check(
            "structured CSV ingestion",
            _count(db, StructuredIngestionBatch) > 0,
            f"batches={_count(db, StructuredIngestionBatch)}",
            "one ready batch",
        ),
        Check(
            "e-invoice lifecycle",
            {"review", "pending", "submitted", "validated"} <= invoice_states,
            f"states={sorted(invoice_states)}",
            "review/pending/submitted/validated",
        ),
        Check(
            "customer outreach workflow",
            {"draft", "pending_approval", "sent", "replied"} <= outreach_states,
            f"states={sorted(outreach_states)}",
            "draft/pending approval/sent/replied",
        ),
        Check(
            "safe Telegram reminder policy",
            bool(policy and policy.telegram_reminders_enabled and policy.require_approval),
            "missing"
            if policy is None
            else f"enabled={policy.telegram_reminders_enabled}, approval={policy.require_approval}",
            "enabled with owner approval required",
        ),
        Check(
            "overdue Telegram reminder",
            overdue_reminders > 0,
            f"reminder actions={overdue_reminders}",
            "one pending-approval reminder",
        ),
        Check(
            "email reply correlation",
            _count(db, EmailReplyCorrelation) > 0,
            f"correlations={_count(db, EmailReplyCorrelation)}",
            "one historical reply",
        ),
        Check(
            "process recommendations",
            {"proposed", "implemented"} <= recommendation_states,
            f"states={sorted(recommendation_states)}",
            "proposed and implemented",
        ),
        Check(
            "conversation evidence persistence",
            _count(db, ConversationTurnCitation) > 0,
            f"citations={_count(db, ConversationTurnCitation)}",
            "persisted turn citations",
        ),
    ]


def print_readiness(checks: list[Check]) -> None:
    print("FinBrain demo-session readiness (read-only)")
    for check in checks:
        marker = "PASS" if check.ready else "GAP "
        print(f"[{marker}] {check.feature}: {check.observed} (need {check.requirement})")
    passed = sum(item.ready for item in checks)
    print(f"\n{passed}/{len(checks)} feature checks ready")


def _ensure_structured_batch(db) -> None:
    result = ingest_structured_csv(db, CSV_PATH.read_bytes(), origin_channel="demo_seed")
    if result.status not in {"ready", "partial"}:
        raise RuntimeError(f"demo_structured_csv_failed:{result.status}")


def _ensure_placeholder_telegram_onboarding(db) -> None:
    """Create a protected, non-deliverable Telegram fixture after a clean reset.

    It exercises onboarding, linking, drafting, and approval safely. Real delivery
    becomes available as soon as an actual user completes /start after startup.
    """
    row = begin_onboarding(
        db,
        tenant_id=DEFAULT_TENANT_ID,
        user_id=PLACEHOLDER_TELEGRAM_ID,
        chat_id=PLACEHOLDER_TELEGRAM_ID,
    )
    if row.status == "awaiting_consent":
        row = accept_consent(db, row.id)
    if row.status == "awaiting_name":
        row = submit_name(db, row.id, "Demo Telegram Customer")
    if row.status == "awaiting_gmail":
        row = submit_gmail(db, row.id, "finbrain.demo.invalid@gmail.com")
    if row.status == "awaiting_phone":
        row = submit_phone(db, row.id, "+601100000001")
    if row.status == "awaiting_message":
        ingest_customer_message(
            db,
            session_id=row.id,
            message_id=1,
            text=("I need a copy of my overdue invoice and want to arrange payment this week."),
        )


def _ensure_luma_email_workflow(db, owner_id: str, finance_id: str) -> None:
    customer = db.scalar(
        select(Customer).where(
            Customer.tenant_id == DEFAULT_TENANT_ID,
            Customer.normalized_name == "luma retail",
        )
    )
    if customer is None:
        # Suffix normalization can evolve; fall back to the deterministic fixture record.
        content = db.scalar(
            select(TokenizedContent).where(
                TokenizedContent.source_record_id == "demo:customer:luma:email:001"
            )
        )
        link = db.scalar(
            select(CustomerRecordLink).where(
                CustomerRecordLink.tokenized_content_id == (content.id if content else -1)
            )
        )
        customer = db.get(Customer, link.customer_id) if link else None
    if customer is None:
        raise RuntimeError("demo_luma_customer_missing")
    endpoint = db.scalar(
        select(CustomerEndpoint)
        .where(
            CustomerEndpoint.tenant_id == DEFAULT_TENANT_ID,
            CustomerEndpoint.customer_id == customer.id,
            CustomerEndpoint.channel == "email",
            CustomerEndpoint.verification_status != "revoked",
        )
        .order_by(CustomerEndpoint.id)
    )
    if endpoint is None:
        raise RuntimeError(f"demo_email_endpoint_missing:{CUSTOMER_EMAIL}")
    if endpoint.verification_status != "verified":
        verify_endpoint(db, endpoint.id, tenant_id=DEFAULT_TENANT_ID, reviewer_id=owner_id)
    evidence_ids = list(
        db.scalars(
            select(CustomerRecordLink.tokenized_content_id)
            .where(
                CustomerRecordLink.tenant_id == DEFAULT_TENANT_ID,
                CustomerRecordLink.customer_id == customer.id,
                CustomerRecordLink.match_status == "verified",
            )
            .order_by(CustomerRecordLink.id)
            .limit(3)
        ).all()
    )
    create_action(
        db,
        tenant_id=DEFAULT_TENANT_ID,
        customer_id=customer.id,
        endpoint_id=endpoint.id,
        subject="Draft customer check-in",
        body="Please review this editable response before submitting it for approval.",
        idempotency_key=SEED_EMAIL_DRAFT_KEY,
        evidence_ids=evidence_ids,
        created_by_user_id=finance_id,
        actor_role=UserRole.FINANCE_OPS.value,
        actor_ref=SEED_ACTOR,
    )
    response = create_action(
        db,
        tenant_id=DEFAULT_TENANT_ID,
        customer_id=customer.id,
        endpoint_id=endpoint.id,
        subject="Delivery reconciliation follow-up",
        body="Please confirm the delivery variance so Finance Operations can reconcile it.",
        idempotency_key=SEED_EMAIL_ACTION_KEY,
        evidence_ids=evidence_ids,
        created_by_user_id=finance_id,
        actor_role=UserRole.FINANCE_OPS.value,
        actor_ref=SEED_ACTOR,
    )
    action = db.get(OutreachAction, response.id)
    if action and action.status == "draft":
        transition_action(
            db,
            action.id,
            "submit",
            tenant_id=DEFAULT_TENANT_ID,
            role=UserRole.FINANCE_OPS,
            user_id=finance_id,
            actor_ref=SEED_ACTOR,
        )


def _ensure_historical_reply(
    db, customer: Customer, endpoint: CustomerEndpoint, evidence_ids: list[int]
) -> None:
    action = db.scalar(
        select(OutreachAction).where(
            OutreachAction.tenant_id == DEFAULT_TENANT_ID,
            OutreachAction.idempotency_key == SEED_REPLIED_ACTION_KEY,
        )
    )
    provider_hash = hashlib.sha256(b"demo-session-provider-message-v1").hexdigest()
    sent_action = db.scalar(
        select(OutreachAction).where(
            OutreachAction.tenant_id == DEFAULT_TENANT_ID,
            OutreachAction.idempotency_key == SEED_SENT_ACTION_KEY,
        )
    )
    if sent_action is None:
        sent_action = OutreachAction(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, SEED_SENT_ACTION_KEY)),
            tenant_id=DEFAULT_TENANT_ID,
            customer_id=customer.id,
            customer_endpoint_id=endpoint.id,
            channel="email",
            protected_subject="Demo sent response",
            protected_body="Historical successfully delivered customer response.",
            status="sent",
            idempotency_key=SEED_SENT_ACTION_KEY,
            created_by_actor_ref=SEED_ACTOR,
            origin_type="manual",
            provider_message_ref_hash=hashlib.sha256(b"demo-session-provider-sent-v1").hexdigest(),
            approved_at=datetime.now(UTC) - timedelta(days=4),
            sent_at=datetime.now(UTC) - timedelta(days=3),
            attempt_count=1,
        )
        db.add(sent_action)
        db.flush()
        for content_id in evidence_ids[:1]:
            db.add(
                OutreachEvidence(
                    tenant_id=DEFAULT_TENANT_ID,
                    outreach_action_id=sent_action.id,
                    tokenized_content_id=content_id,
                    purpose="supporting",
                )
            )
    if action is None:
        action = OutreachAction(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, SEED_REPLIED_ACTION_KEY)),
            tenant_id=DEFAULT_TENANT_ID,
            customer_id=customer.id,
            customer_endpoint_id=endpoint.id,
            channel="email",
            protected_subject="Demo historical follow-up",
            protected_body="Demo customer response history.",
            status="replied",
            idempotency_key=SEED_REPLIED_ACTION_KEY,
            created_by_actor_ref=SEED_ACTOR,
            origin_type="manual",
            provider_message_ref_hash=provider_hash,
            approved_at=datetime.now(UTC) - timedelta(days=3),
            sent_at=datetime.now(UTC) - timedelta(days=2),
            replied_at=datetime.now(UTC) - timedelta(days=1),
            attempt_count=1,
        )
        db.add(action)
        db.flush()
        for content_id in evidence_ids[:1]:
            db.add(
                OutreachEvidence(
                    tenant_id=DEFAULT_TENANT_ID,
                    outreach_action_id=action.id,
                    tokenized_content_id=content_id,
                    purpose="supporting",
                )
            )
    reply_content = db.scalar(
        select(TokenizedContent).where(
            TokenizedContent.source_record_id == "demo:email:reply-correlation:001"
        )
    )
    if reply_content is None:
        # Re-use already protected customer evidence; the correlation table is the
        # workflow fixture, while raw mailbox content remains connector-owned.
        reply_content = db.get(TokenizedContent, evidence_ids[0])
    receipt_hash = hashlib.sha256(b"demo-session-email-receipt-v1").hexdigest()
    receipt = db.get(EmailIngestionReceipt, receipt_hash)
    if receipt is None:
        receipt = EmailIngestionReceipt(
            message_ref_hash=receipt_hash,
            status="ready",
            source_record_id=None,
            processed_at=datetime.now(UTC) - timedelta(days=1),
            customer_id=customer.id,
            outreach_action_id=action.id,
            in_reply_to_ref_hash=provider_hash,
            correlation_status="correlated",
            correlated_at=datetime.now(UTC) - timedelta(days=1),
        )
        db.add(receipt)
    existing = db.scalar(
        select(EmailReplyCorrelation).where(
            EmailReplyCorrelation.email_receipt_ref_hash == receipt_hash,
            EmailReplyCorrelation.outreach_action_id == action.id,
        )
    )
    if existing is None:
        db.add(
            EmailReplyCorrelation(
                tenant_id=DEFAULT_TENANT_ID,
                email_receipt_ref_hash=receipt_hash,
                outreach_action_id=action.id,
                matched_reference_hash=provider_hash,
                customer_id=customer.id,
                tokenized_content_id=reply_content.id,
                status="correlated",
            )
        )
    db.commit()


def _ensure_telegram_invoice_and_policy(db, owner_id: str) -> None:
    endpoint = db.scalar(
        select(CustomerEndpoint)
        .join(Customer, Customer.id == CustomerEndpoint.customer_id)
        .where(
            CustomerEndpoint.tenant_id == DEFAULT_TENANT_ID,
            CustomerEndpoint.channel == "telegram",
            CustomerEndpoint.verification_status == "verified",
            CustomerEndpoint.delivery_token.is_not(None),
            Customer.profile_status == "confirmed",
            Customer.identity_review_status == "clear",
        )
        .order_by(CustomerEndpoint.id)
    )
    if endpoint is None:
        raise RuntimeError(
            "real_telegram_onboarding_required: complete /start onboarding before --apply"
        )
    invoice = db.scalar(
        select(EInvoiceRecord).where(
            EInvoiceRecord.tenant_id == DEFAULT_TENANT_ID,
            EInvoiceRecord.invoice_no == SEED_TELEGRAM_INVOICE,
        )
    )
    as_of = date.today()
    if invoice is None:
        invoice = EInvoiceRecord(
            tenant_id=DEFAULT_TENANT_ID,
            supplier_name="FinBrain Demo Supplier Sdn Bhd",
            supplier_tin="C2026082101",
            buyer_name="Protected Telegram customer",
            buyer_customer_id=endpoint.customer_id,
            invoice_no=SEED_TELEGRAM_INVOICE,
            issue_date=as_of - timedelta(days=50),
            due_date=as_of - timedelta(days=35),
            currency="MYR",
            tax_type="SST",
            tax_rate="6%",
            total_amount=Decimal("12500.00"),
            status="validated",
            uin="MY29ADEMOTG",
        )
        db.add(invoice)
    else:
        invoice.buyer_customer_id = endpoint.customer_id
        invoice.due_date = as_of - timedelta(days=35)
        invoice.status = "validated"
        invoice.paid_at = None
    db.commit()
    sync_einvoice_tokenized_content(db, invoice)
    policy = db.get(TenantOutreachPolicy, DEFAULT_TENANT_ID)
    if policy is None:
        policy = TenantOutreachPolicy(
            tenant_id=DEFAULT_TENANT_ID,
            telegram_reminders_enabled=True,
            grace_days=1,
            repeat_interval_days=30,
            max_reminders=3,
            require_approval=True,
            policy_version=1,
            updated_by_user_id=owner_id,
        )
        db.add(policy)
        db.commit()
    elif not policy.telegram_reminders_enabled or not policy.require_approval:
        raise RuntimeError(
            "existing_outreach_policy_is_not_demo_safe: owner must enable Telegram and approval"
        )


def _ensure_worker_owned_scenarios(db) -> None:
    """Create connector/worker-owned history under the worker RLS role."""
    customer = db.scalar(
        select(Customer)
        .join(CustomerEndpoint, CustomerEndpoint.customer_id == Customer.id)
        .where(
            Customer.tenant_id == DEFAULT_TENANT_ID,
            CustomerEndpoint.channel == "email",
            CustomerEndpoint.verification_status == "verified",
        )
        .order_by(Customer.id)
    )
    if customer is None:
        raise RuntimeError("verified_email_customer_missing")
    endpoint = db.scalar(
        select(CustomerEndpoint).where(
            CustomerEndpoint.tenant_id == DEFAULT_TENANT_ID,
            CustomerEndpoint.customer_id == customer.id,
            CustomerEndpoint.channel == "email",
            CustomerEndpoint.verification_status == "verified",
        )
    )
    evidence_ids = list(
        db.scalars(
            select(CustomerRecordLink.tokenized_content_id)
            .where(
                CustomerRecordLink.tenant_id == DEFAULT_TENANT_ID,
                CustomerRecordLink.customer_id == customer.id,
                CustomerRecordLink.match_status == "verified",
            )
            .order_by(CustomerRecordLink.id)
            .limit(1)
        ).all()
    )
    if endpoint is None or not evidence_ids:
        raise RuntimeError("historical_email_reply_prerequisites_missing")
    _ensure_historical_reply(db, customer, endpoint, evidence_ids)

    invoice = db.scalar(
        select(EInvoiceRecord).where(
            EInvoiceRecord.tenant_id == DEFAULT_TENANT_ID,
            EInvoiceRecord.invoice_no == SEED_TELEGRAM_INVOICE,
        )
    )
    result = plan_due_reminders(db, DEFAULT_TENANT_ID, date.today())
    if invoice is None or (
        result.eligible == 0
        and _count(
            db,
            OutreachAction,
            OutreachAction.tenant_id == DEFAULT_TENANT_ID,
            OutreachAction.origin_invoice_id == invoice.id,
        )
        == 0
    ):
        raise RuntimeError("telegram_reminder_was_not_eligible")


def _ensure_recommendations_and_conversation(db, owner_id: str) -> None:
    evidence = list(
        db.scalars(
            select(TokenizedContent)
            .where(
                TokenizedContent.tenant_id == DEFAULT_TENANT_ID,
                TokenizedContent.processing_status == "ready",
            )
            .order_by(TokenizedContent.id)
            .limit(3)
        ).all()
    )
    if not evidence:
        raise RuntimeError("protected_demo_evidence_missing")
    now = datetime.now(UTC)
    for status in ("proposed", "implemented"):
        fingerprint = hashlib.sha256(
            f"demo-session-recommendation:{status}:v1".encode()
        ).hexdigest()
        row = db.scalar(
            select(ProcessRecommendation).where(ProcessRecommendation.fingerprint == fingerprint)
        )
        if row is None:
            row = ProcessRecommendation(
                tenant_id=DEFAULT_TENANT_ID,
                fingerprint=fingerprint,
                title=f"Demo {status} process improvement",
                problem_statement="Protected records show repeatable follow-up work.",
                recommendation="Use a governed owner queue and measurable resolution target.",
                expected_benefit="Faster, auditable resolution.",
                suggested_owner="Finance Operations",
                success_metric="Reduce unresolved follow-ups by 50% in 30 days.",
                category="demo_followup",
                priority="medium",
                confidence=0.9,
                status=status,
                analysis_window_start=now - timedelta(days=30),
                analysis_window_end=now,
                record_count=len(evidence),
                source_systems=sorted({item.source_system for item in evidence}),
                enrichment_mode="demo-seed",
                created_by_user_id=owner_id,
            )
            db.add(row)
            db.flush()
            for content in evidence:
                db.add(
                    RecommendationEvidence(
                        tenant_id=DEFAULT_TENANT_ID,
                        recommendation_id=row.id,
                        tokenized_content_id=content.id,
                        evidence_excerpt=(content.summary or content.content_text)[:500],
                        relevance_reason="Seeded cross-source workflow evidence.",
                    )
                )
            if status == "implemented":
                for decision in ("approved", "implemented"):
                    db.add(
                        RecommendationDecision(
                            tenant_id=DEFAULT_TENANT_ID,
                            recommendation_id=row.id,
                            decision=decision,
                            actor_role=UserRole.OWNER_DIRECTOR.value,
                            actor_ref=SEED_ACTOR,
                        )
                    )
            write_workflow_event(
                db,
                event_type="demo_recommendation_seeded",
                actor_role=UserRole.OWNER_DIRECTOR.value,
                actor_ref=SEED_ACTOR,
                resource_type="process_recommendation",
                resource_id=str(row.id),
                tenant_id=DEFAULT_TENANT_ID,
                event_payload={"status": status, "evidence_count": len(evidence)},
            )
            db.commit()
    conversation = db.get(Conversation, SEED_CONVERSATION_ID)
    if conversation is None:
        conversation = Conversation(
            id=SEED_CONVERSATION_ID,
            tenant_id=DEFAULT_TENANT_ID,
            created_by_user_id=owner_id,
            status="active",
            expires_at=now + timedelta(days=30),
        )
        db.add(conversation)
        db.flush()
        turn = ConversationTurn(
            tenant_id=DEFAULT_TENANT_ID,
            conversation_id=conversation.id,
            sequence_number=1,
            user_role=UserRole.OWNER_DIRECTOR.value,
            protected_question="Show the protected demo sources.",
            protected_answer="The cited records demonstrate cross-source evidence persistence.",
            query_intent="source_listing",
            source_systems=sorted({item.source_system for item in evidence}),
            reasoning_mode="sql-first",
            insufficient_evidence=False,
        )
        db.add(turn)
        db.flush()
        for ordinal, content in enumerate(evidence, 1):
            db.add(
                ConversationTurnCitation(
                    tenant_id=DEFAULT_TENANT_ID,
                    turn_id=turn.id,
                    ordinal=ordinal,
                    tokenized_content_id=content.id,
                )
            )
        db.commit()


def _ensure_legacy_draft_states(db, owner_id: str) -> None:
    invoice = db.scalar(
        select(EInvoiceRecord)
        .where(EInvoiceRecord.tenant_id == DEFAULT_TENANT_ID)
        .order_by(EInvoiceRecord.id)
    )
    if invoice is None:
        return
    for status in ("draft", "approved", "rejected"):
        marker = f"[demo-session:{status}]"
        existing = db.scalar(
            select(EinvoiceOutreachDraft).where(
                EinvoiceOutreachDraft.einvoice_record_id == invoice.id,
                EinvoiceOutreachDraft.draft_text == marker,
            )
        )
        if existing is None:
            db.add(
                EinvoiceOutreachDraft(
                    tenant_id=DEFAULT_TENANT_ID,
                    einvoice_record_id=invoice.id,
                    channel="email",
                    draft_text=marker,
                    status=status,
                    created_by_user_id=owner_id,
                    decided_by_user_id=owner_id if status != "draft" else None,
                    decided_at=datetime.now(UTC) if status != "draft" else None,
                )
            )
    db.commit()


def apply_demo_session(*, reset: bool = False) -> None:
    """Apply complete demo coverage, optionally from a clean application database."""
    seed_base_data(reset=reset)
    if reset:
        with SessionLocal() as db:
            set_worker_context(db, actor_ref=SEED_ACTOR, tenant_id=DEFAULT_TENANT_ID)
            _ensure_placeholder_telegram_onboarding(db)
    seed_demo_customer()
    with SessionLocal() as db:
        owner_id = _owner_id(db)
        finance_id = _finance_id(db)
        if not owner_id or not finance_id:
            raise RuntimeError("active_owner_and_finance_auth_roles_required")
        set_rls_context(
            db,
            user_id=owner_id,
            user_role=UserRole.OWNER_DIRECTOR.value,
            actor_ref=SEED_ACTOR,
            tenant_id=DEFAULT_TENANT_ID,
        )
        _ensure_structured_batch(db)
        _ensure_luma_email_workflow(db, owner_id, finance_id)
        _ensure_telegram_invoice_and_policy(db, owner_id)
        _ensure_recommendations_and_conversation(db, owner_id)
        _ensure_legacy_draft_states(db, owner_id)
    with SessionLocal() as db:
        set_worker_context(db, actor_ref=SEED_ACTOR, tenant_id=DEFAULT_TENANT_ID)
        _ensure_worker_owned_scenarios(db)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or idempotently prepare complete FinBrain demo-session data."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Add seed-owned fixtures. Without this flag the command is read-only.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear application history before applying a clean demo dataset.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required confirmation for the destructive --reset operation.",
    )
    args = parser.parse_args()
    if args.reset and not args.apply:
        parser.error("--reset requires --apply")
    if args.reset and not args.yes:
        parser.error("--reset requires --yes because it clears application history")
    initialize_local_schema()
    if args.apply:
        apply_demo_session(reset=args.reset)
    with SessionLocal() as db:
        roles = set(
            db.scalars(
                select(AuthUserRole.user_role).where(
                    AuthUserRole.tenant_id == DEFAULT_TENANT_ID,
                    AuthUserRole.active.is_(True),
                )
            ).all()
        )
        owner_id = _owner_id(db)
        if owner_id:
            set_rls_context(
                db,
                user_id=owner_id,
                user_role=UserRole.OWNER_DIRECTOR.value,
                actor_ref=SEED_ACTOR,
                tenant_id=DEFAULT_TENANT_ID,
            )
        checks = collect_readiness(db, active_roles=roles)
    print_readiness(checks)
    return 0 if all(item.ready for item in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
