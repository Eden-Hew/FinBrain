import hashlib
import hmac
import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    CustomerIdentityClaim,
    CustomerRecordLink,
    TelegramOnboardingSession,
    TokenizedContent,
)
from app.schemas import CanonicalIngestionRecord, UserRole
from app.security.detokenize import detokenize_response_with_trace, hash_query
from app.security.tokenize import protect_scalar
from app.services.customer_endpoint_resolution import EndpointEvidence, resolve_customer_endpoint
from app.services.ingestion import enrich_protected_record, protect_canonical_record

GMAIL_PATTERN = re.compile(r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@gmail\.com$", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9 -]{7,19}$")


def _opaque(value: str, purpose: str) -> str:
    return hmac.new(
        get_settings().token_root_secret.encode(),
        f"{purpose}:{value}".encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


def _session(db: Session, session_id: int) -> TelegramOnboardingSession:
    row = db.get(TelegramOnboardingSession, session_id)
    if row is None:
        raise LookupError("telegram_onboarding_not_found")
    return row


def _expect(row: TelegramOnboardingSession, status: str) -> None:
    if row.status != status:
        raise ValueError(f"telegram_onboarding_expected_{status}")


def _repair_completed_identity(
    db: Session, row: TelegramOnboardingSession
) -> TelegramOnboardingSession:
    """Backfill identity claims omitted by the initial Telegram implementation."""
    if (
        row.status not in {"awaiting_message", "completed"}
        or row.customer_id is None
        or row.profile_content_id is None
        or row.name_token is None
        or row.email_token is None
        or row.phone_token is None
    ):
        return row
    claim_exists = db.scalar(
        select(CustomerIdentityClaim.id).where(
            CustomerIdentityClaim.tenant_id == row.tenant_id,
            CustomerIdentityClaim.customer_id == row.customer_id,
            CustomerIdentityClaim.identity_token == row.name_token,
            CustomerIdentityClaim.claim_basis == "self_identification",
        )
    )
    if claim_exists is not None:
        return row
    resolve_customer_endpoint(
        db,
        EndpointEvidence(
            tenant_id=row.tenant_id,
            name_token=row.name_token,
            email_token=row.email_token,
            phone_token=row.phone_token,
            telegram_endpoint_token=row.telegram_endpoint_token,
            telegram_delivery_token=row.telegram_delivery_token,
            evidence_content_id=row.profile_content_id,
        ),
    )
    return _session(db, row.id)


def begin_onboarding(
    db: Session, *, tenant_id: str, user_id: int, chat_id: int
) -> TelegramOnboardingSession:
    source_id = f"telegram:onboarding:{_opaque(f'{tenant_id}:{user_id}', 'onboarding')}"
    user_token = protect_scalar(
        db,
        entity_type="TGUSER",
        value=str(user_id),
        source_record_id=source_id,
        tenant_id=tenant_id,
    )
    chat_token = protect_scalar(
        db,
        entity_type="TGCHAT",
        value=str(chat_id),
        source_record_id=source_id,
        tenant_id=tenant_id,
    )
    row = db.scalar(
        select(TelegramOnboardingSession).where(
            TelegramOnboardingSession.tenant_id == tenant_id,
            TelegramOnboardingSession.telegram_endpoint_token == user_token,
        )
    )
    if row is None:
        row = TelegramOnboardingSession(
            tenant_id=tenant_id,
            telegram_endpoint_token=user_token,
            telegram_delivery_token=chat_token,
            status="awaiting_consent",
        )
        db.add(row)
    else:
        row.telegram_delivery_token = chat_token
        if row.status in {"cancelled", "failed"}:
            row.status = "awaiting_consent"
            row.failure_code = None
        elif row.status == "reconciling":
            # Reconciliation may be interrupted after the protected phone token
            # is committed. Asking for the phone again safely replays the
            # deterministic protected operation without losing prior inputs.
            row.status = "awaiting_phone"
            row.failure_code = "telegram_reconciliation_interrupted"
        else:
            row = _repair_completed_identity(db, row)
    db.commit()
    return row


def accept_consent(db: Session, session_id: int) -> TelegramOnboardingSession:
    row = _session(db, session_id)
    _expect(row, "awaiting_consent")
    row.status = "awaiting_name"
    row.consented_at = datetime.now(UTC)
    db.commit()
    return row


def cancel_onboarding(db: Session, session_id: int) -> TelegramOnboardingSession:
    row = _session(db, session_id)
    row.status = "cancelled"
    row.failure_code = None
    db.commit()
    return row


def customer_display_name(db: Session, onboarding: TelegramOnboardingSession) -> str | None:
    """Restore the connected customer's own name for a direct Telegram greeting."""
    if (
        onboarding.status not in {"awaiting_message", "completed"}
        or onboarding.customer_id is None
        or onboarding.name_token is None
    ):
        return None
    trace = detokenize_response_with_trace(
        db,
        onboarding.name_token,
        UserRole.GENERAL_EMPLOYEE.value,
        hash_query(f"telegram-customer-greeting:{onboarding.id}"),
        actor_ref=f"telegram-customer:{onboarding.telegram_endpoint_token[-10:]}",
        turn_ref=f"telegram-onboarding:{onboarding.id}:greeting",
    )
    if trace.restored_tokens != 1 or trace.withheld_tokens != 0:
        return None
    return trace.text


def submit_name(db: Session, session_id: int, name: str) -> TelegramOnboardingSession:
    row = _session(db, session_id)
    _expect(row, "awaiting_name")
    cleaned = " ".join(name.split())
    if len(cleaned) < 2 or len(cleaned) > 120 or any(char.isdigit() for char in cleaned):
        raise ValueError("valid_customer_name_required")
    source_id = f"telegram:onboarding:{row.telegram_endpoint_token.rsplit('_', 1)[-1]}"
    row.name_token = protect_scalar(
        db,
        entity_type="PERSON",
        value=cleaned,
        source_record_id=source_id,
        tenant_id=row.tenant_id,
    )
    row.status = "awaiting_gmail"
    db.commit()
    return row


def submit_gmail(db: Session, session_id: int, gmail: str) -> TelegramOnboardingSession:
    row = _session(db, session_id)
    _expect(row, "awaiting_gmail")
    cleaned = gmail.strip().casefold()
    if not GMAIL_PATTERN.fullmatch(cleaned):
        raise ValueError("valid_gmail_required")
    source_id = f"telegram:onboarding:{row.telegram_endpoint_token.rsplit('_', 1)[-1]}"
    row.email_token = protect_scalar(
        db,
        entity_type="EMAIL",
        value=cleaned,
        source_record_id=source_id,
        tenant_id=row.tenant_id,
    )
    row.status = "awaiting_phone"
    db.commit()
    return row


def submit_phone(db: Session, session_id: int, phone: str) -> TelegramOnboardingSession:
    row = _session(db, session_id)
    _expect(row, "awaiting_phone")
    cleaned = phone.strip()
    if not PHONE_PATTERN.fullmatch(cleaned):
        raise ValueError("valid_phone_required")
    if row.name_token is None or row.email_token is None:
        raise ValueError("incomplete_telegram_identity")
    source_id = f"telegram:onboarding:{row.telegram_endpoint_token.rsplit('_', 1)[-1]}"
    row.phone_token = protect_scalar(
        db,
        entity_type="PHONE",
        value=cleaned,
        source_record_id=source_id,
        tenant_id=row.tenant_id,
    )
    row.status = "reconciling"
    db.commit()

    protected_profile = "\n".join(
        (
            f"Customer name: {row.name_token}",
            f"Gmail: {row.email_token}",
            f"Phone: {row.phone_token}",
            f"Telegram identity: {row.telegram_endpoint_token}",
        )
    )
    result = protect_canonical_record(
        db,
        CanonicalIngestionRecord(
            source_record_id=source_id,
            source_system="telegram",
            record_type="customer_onboarding_profile",
            text=protected_profile,
            tenant_id=row.tenant_id,
            metadata={"channel": "telegram_private", "identity_bundle": "complete"},
        ),
    )
    content = db.scalar(
        select(TokenizedContent).where(TokenizedContent.source_record_id == result.source_record_id)
    )
    if content is None:
        raise RuntimeError("telegram_onboarding_profile_missing")
    resolved = resolve_customer_endpoint(
        db,
        EndpointEvidence(
            tenant_id=row.tenant_id,
            name_token=row.name_token,
            email_token=row.email_token,
            phone_token=row.phone_token,
            telegram_endpoint_token=row.telegram_endpoint_token,
            telegram_delivery_token=row.telegram_delivery_token,
            evidence_content_id=content.id,
        ),
    )
    row = _session(db, session_id)
    row.customer_id = resolved.customer_id
    row.profile_content_id = content.id
    row.status = "awaiting_message"
    db.commit()
    enrich_protected_record(db, result.source_record_id)
    return row


def ingest_customer_message(
    db: Session, *, session_id: int, message_id: int, text: str
) -> TokenizedContent:
    row = _session(db, session_id)
    if row.status not in {"awaiting_message", "completed"} or row.customer_id is None:
        raise ValueError("telegram_customer_profile_incomplete")
    source_id = f"telegram:{_opaque(f'{row.telegram_endpoint_token}:{message_id}', 'message')}"
    result = protect_canonical_record(
        db,
        CanonicalIngestionRecord(
            source_record_id=source_id,
            source_system="telegram",
            record_type="customer_message",
            text=text,
            tenant_id=row.tenant_id,
            metadata={"channel": "telegram_private"},
        ),
    )
    content = db.scalar(
        select(TokenizedContent).where(TokenizedContent.source_record_id == result.source_record_id)
    )
    if content is None:
        raise RuntimeError("telegram_customer_message_missing")
    link = db.scalar(
        select(CustomerRecordLink).where(
            CustomerRecordLink.tenant_id == row.tenant_id,
            CustomerRecordLink.customer_id == row.customer_id,
            CustomerRecordLink.tokenized_content_id == content.id,
            CustomerRecordLink.match_basis == "verified_telegram_endpoint",
        )
    )
    if link is None:
        db.add(
            CustomerRecordLink(
                tenant_id=row.tenant_id,
                customer_id=row.customer_id,
                tokenized_content_id=content.id,
                match_status="verified",
                confidence=1.0,
                match_basis="verified_telegram_endpoint",
            )
        )
    row.status = "completed"
    row.completed_at = row.completed_at or datetime.now(UTC)
    db.commit()
    enrich_protected_record(db, result.source_record_id)
    return content
