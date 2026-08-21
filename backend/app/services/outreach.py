import re
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Conversation,
    ConversationTurn,
    ConversationTurnCitation,
    Customer,
    CustomerAlias,
    CustomerEndpoint,
    CustomerIdentityClaim,
    CustomerRecordLink,
    OutreachAction,
    OutreachEvidence,
    ProtectedTokenRegistry,
    TokenizedContent,
)
from app.schemas import OutreachActionResponse, UserRole
from app.security.detect import contains_known_pii
from app.security.detokenize import TOKEN_PATTERN
from app.security.protection import protect_text
from app.security.tokenize import persist_vault_entries, protect_scalar
from app.services.morpheus import morpheus_chat
from app.services.reasoning import unknown_tokens
from app.services.workflow_audit import write_workflow_event


class GeneratedOutreachDraft(BaseModel):
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(min_length=1, max_length=20_000)


_SUPPORTED_OUTREACH_CHANNELS = {"email", "telegram"}


def _validate_outreach_endpoint(
    db: Session,
    *,
    tenant_id: str,
    customer_id: int,
    endpoint_id: int,
    require_verified: bool,
) -> CustomerEndpoint:
    endpoint = db.get(CustomerEndpoint, endpoint_id)
    if (
        endpoint is None
        or endpoint.tenant_id != tenant_id
        or endpoint.customer_id != customer_id
    ):
        raise LookupError("customer_endpoint_not_found")
    if endpoint.channel not in _SUPPORTED_OUTREACH_CHANNELS:
        raise ValueError("unsupported_outreach_channel")
    if require_verified and endpoint.verification_status != "verified":
        raise ValueError("verified_outreach_endpoint_required")
    if endpoint.channel == "telegram" and endpoint.delivery_token is None:
        raise ValueError("telegram_delivery_destination_required")
    return endpoint


_CUSTOMER_CONTACT_MISUSE = re.compile(
    r"\bcontact\s+(?:us|our\s+(?:company|team))\b.*"
    r"(?:PHONE_[0-9a-f]{10}|EMAIL_[0-9a-f]{10}|"
    r"phone number you provided|email address you provided)",
    re.IGNORECASE,
)


def _remove_customer_contact_misuse(body: str) -> str:
    """Drop model-authored lines that present customer contacts as company contacts."""
    kept = [line for line in body.splitlines() if not _CUSTOMER_CONTACT_MISUSE.search(line)]
    return "\n".join(kept).strip()


def _response(db: Session, row: OutreachAction) -> OutreachActionResponse:
    return OutreachActionResponse.model_validate(
        {
            "id": row.id,
            "customer_id": row.customer_id,
            "customer_endpoint_id": row.customer_endpoint_id,
            "channel": row.channel,
            "protected_subject": row.protected_subject,
            "protected_body": row.protected_body,
            "status": row.status,
            "idempotency_key": row.idempotency_key,
            "attempt_count": row.attempt_count,
            "failure_code": row.failure_code,
            "created_at": row.created_at,
            "approved_at": row.approved_at,
            "sent_at": row.sent_at,
            "replied_at": row.replied_at,
        }
    )


def get_action(db: Session, action_id: str, *, tenant_id: str) -> OutreachActionResponse:
    row = db.get(OutreachAction, action_id)
    if row is None or row.tenant_id != tenant_id:
        raise LookupError("outreach_action_not_found")
    return _response(db, row)


def register_email_endpoint(
    db: Session, *, tenant_id: str, customer_id: int, value: str,
    actor_role: str = "system", actor_ref: str = "system",
) -> CustomerEndpoint:
    customer = db.get(Customer, customer_id)
    if customer is None or customer.tenant_id != tenant_id:
        raise LookupError("customer_not_found")
    source_id = f"customer-endpoint:{uuid.uuid4()}"
    protected, entries = protect_text(value.strip(), source_id, tenant_id, db)
    tokens = TOKEN_PATTERN.findall(protected)
    if len(tokens) != 1 or protected.strip() != tokens[0] or not tokens[0].startswith("EMAIL_"):
        raise ValueError("valid_email_endpoint_required")
    persist_vault_entries(db, entries)
    existing = db.scalar(
        select(CustomerEndpoint).where(
            CustomerEndpoint.tenant_id == tenant_id,
            CustomerEndpoint.channel == "email",
            CustomerEndpoint.endpoint_token == tokens[0],
        )
    )
    if existing:
        if existing.customer_id != customer_id:
            raise ValueError("email_endpoint_already_owned")
        if existing.verification_status == "revoked":
            existing.verification_status = "observed"
            existing.verified_by_user_id = None
            existing.verified_at = None
            write_workflow_event(
                db, event_type="customer_endpoint_restored", actor_role=actor_role,
                actor_ref=actor_ref, resource_type="customer_endpoint",
                resource_id=str(existing.id), tenant_id=tenant_id,
                event_payload={"customer_id": customer_id, "channel": "email"},
            )
        db.commit()
        return existing
    row = CustomerEndpoint(
        tenant_id=tenant_id, customer_id=customer_id, channel="email",
        endpoint_token=tokens[0], verification_status="observed",
    )
    db.add(row)
    db.commit()
    return row


def revoke_endpoint(
    db: Session, endpoint_id: int, *, tenant_id: str,
    actor_role: str, actor_ref: str,
) -> CustomerEndpoint:
    row = db.get(CustomerEndpoint, endpoint_id)
    if row is None or row.tenant_id != tenant_id:
        raise LookupError("customer_endpoint_not_found")
    if row.verification_status == "revoked":
        return row
    previous_status = row.verification_status
    row.verification_status = "revoked"
    write_workflow_event(
        db, event_type="customer_endpoint_revoked", actor_role=actor_role,
        actor_ref=actor_ref, resource_type="customer_endpoint",
        resource_id=str(row.id), tenant_id=tenant_id,
        event_payload={
            "customer_id": row.customer_id,
            "channel": row.channel,
            "previous_status": previous_status,
            "status": "revoked",
        },
    )
    db.commit()
    return row


def verify_endpoint(
    db: Session, endpoint_id: int, *, tenant_id: str, reviewer_id: str
) -> CustomerEndpoint:
    row = db.get(CustomerEndpoint, endpoint_id)
    if row is None or row.tenant_id != tenant_id:
        raise LookupError("customer_endpoint_not_found")
    if row.verification_status == "revoked":
        raise ValueError("revoked_endpoint_cannot_be_verified")
    row.verification_status = "verified"
    row.verified_by_user_id = reviewer_id
    row.verified_at = datetime.now(UTC)
    customer = db.get(Customer, row.customer_id)
    if customer is not None and customer.identity_review_status == "clear":
        customer.profile_status = "confirmed"
    db.commit()
    return row


def resolve_identity_claim(
    db: Session,
    claim_id: int,
    *,
    tenant_id: str,
    decision: str,
    reviewer_id: str,
    actor_ref: str,
) -> CustomerIdentityClaim:
    claim = db.get(CustomerIdentityClaim, claim_id)
    if claim is None or claim.tenant_id != tenant_id:
        raise LookupError("customer_identity_claim_not_found")
    if decision not in {"accept_primary", "accept_alias", "reject"}:
        raise ValueError("unsupported_identity_claim_decision")
    customer = db.get(Customer, claim.customer_id)
    if customer is None:
        raise LookupError("customer_not_found")
    now = datetime.now(UTC)
    if decision == "accept_primary":
        customer.primary_name_token = claim.identity_token
        claim.status = "accepted"
        for other in db.scalars(
            select(CustomerIdentityClaim).where(
                CustomerIdentityClaim.tenant_id == tenant_id,
                CustomerIdentityClaim.customer_id == customer.id,
                CustomerIdentityClaim.id != claim.id,
                CustomerIdentityClaim.status.in_(("observed", "conflicting")),
                CustomerIdentityClaim.identity_token != claim.identity_token,
            )
        ).all():
            other.status = "rejected"
            other.reviewed_by_user_id = reviewer_id
            other.reviewed_at = now
    elif decision == "accept_alias":
        existing_alias = db.scalar(
            select(CustomerAlias).where(
                CustomerAlias.tenant_id == tenant_id,
                CustomerAlias.customer_id == customer.id,
                CustomerAlias.alias_token == claim.identity_token,
            )
        )
        if existing_alias is None:
            db.add(
                CustomerAlias(
                    tenant_id=tenant_id,
                    customer_id=customer.id,
                    alias_token=claim.identity_token,
                    alias_type="email_identity_claim",
                    match_status="verified",
                    confidence=claim.confidence,
                    source_system="email",
                    source_record_id=str(claim.evidence_content_id),
                    reviewed_by_user_id=reviewer_id,
                    reviewed_at=now,
                )
            )
        claim.status = "accepted"
    else:
        claim.status = "rejected"
    claim.reviewed_by_user_id = reviewer_id
    claim.reviewed_at = now
    unresolved = db.scalars(
        select(CustomerIdentityClaim).where(
            CustomerIdentityClaim.tenant_id == tenant_id,
            CustomerIdentityClaim.customer_id == customer.id,
            CustomerIdentityClaim.id != claim.id,
            CustomerIdentityClaim.status == "conflicting",
        )
    ).all()
    customer.identity_review_status = "review_required" if unresolved else "clear"
    if customer.identity_review_status == "clear":
        customer.profile_status = "confirmed"
    write_workflow_event(
        db,
        event_type="customer_identity_claim_resolved",
        actor_role=UserRole.OWNER_DIRECTOR.value,
        actor_ref=actor_ref,
        resource_type="customer_identity_claim",
        resource_id=str(claim.id),
        tenant_id=tenant_id,
        event_payload={"customer_id": customer.id, "decision": decision},
    )
    db.commit()
    return claim


def create_action(
    db: Session, *, tenant_id: str, customer_id: int, endpoint_id: int,
    subject: str, body: str, idempotency_key: str, evidence_ids: list[int],
    created_by_user_id: str, actor_role: str, actor_ref: str,
) -> OutreachActionResponse:
    existing = db.scalar(select(OutreachAction).where(
        OutreachAction.tenant_id == tenant_id,
        OutreachAction.idempotency_key == idempotency_key,
    ))
    if existing:
        return _response(db, existing)
    endpoint = _validate_outreach_endpoint(
        db,
        tenant_id=tenant_id,
        customer_id=customer_id,
        endpoint_id=endpoint_id,
        require_verified=False,
    )
    action_id = str(uuid.uuid4())
    subject_protected, subject_entries = protect_text(
        subject, f"outreach-subject:{action_id}", tenant_id, db
    )
    body_protected, body_entries = protect_text(
        body, f"outreach-body:{action_id}", tenant_id, db
    )
    persist_vault_entries(db, [*subject_entries, *body_entries])
    evidence_rows = db.scalars(select(TokenizedContent).where(
        TokenizedContent.tenant_id == tenant_id,
        TokenizedContent.id.in_(evidence_ids or [-1]),
        TokenizedContent.processing_status == "ready",
    )).all()
    if len(evidence_rows) != len(set(evidence_ids)):
        raise ValueError("invalid_outreach_evidence")
    linked_ids = set(db.scalars(select(CustomerRecordLink.tokenized_content_id).where(
        CustomerRecordLink.tenant_id == tenant_id,
        CustomerRecordLink.customer_id == customer_id,
        CustomerRecordLink.match_status == "verified",
        CustomerRecordLink.tokenized_content_id.in_(evidence_ids or [-1]),
    )).all())
    if set(evidence_ids) - linked_ids:
        raise ValueError("outreach_evidence_not_linked_to_customer")
    row = OutreachAction(
        id=action_id, tenant_id=tenant_id, customer_id=customer_id,
        customer_endpoint_id=endpoint_id, channel=endpoint.channel,
        protected_subject=subject_protected, protected_body=body_protected,
        status="draft", idempotency_key=idempotency_key,
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    db.flush()
    for content_id in dict.fromkeys(evidence_ids):
        db.add(OutreachEvidence(
            tenant_id=tenant_id, outreach_action_id=row.id,
            tokenized_content_id=content_id, purpose="supporting",
        ))
    write_workflow_event(
        db, event_type="outreach_drafted", actor_role=actor_role,
        actor_ref=actor_ref, resource_type="outreach_action", resource_id=row.id,
        tenant_id=tenant_id,
        event_payload={
            "customer_id": customer_id,
            "channel": endpoint.channel,
            "evidence_count": len(evidence_ids),
        },
    )
    db.commit()
    return _response(db, row)


def _turn_evidence_ids(
    db: Session, *, tenant_id: str, customer_id: int, turn_id: int | None
) -> list[int]:
    linked = (
        select(CustomerRecordLink.tokenized_content_id)
        .join(
            TokenizedContent,
            TokenizedContent.id == CustomerRecordLink.tokenized_content_id,
        )
        .where(
            CustomerRecordLink.tenant_id == tenant_id,
            CustomerRecordLink.customer_id == customer_id,
            CustomerRecordLink.match_status == "verified",
            TokenizedContent.tenant_id == tenant_id,
            TokenizedContent.processing_status == "ready",
        )
    )
    if turn_id is not None:
        turn = db.get(ConversationTurn, turn_id)
        conversation = db.get(Conversation, turn.conversation_id) if turn is not None else None
        if (
            turn is None
            or turn.tenant_id != tenant_id
            or conversation is None
            or conversation.tenant_id != tenant_id
            or conversation.context_customer_id != customer_id
        ):
            raise ValueError("outreach_turn_not_in_customer_context")
        cited = select(ConversationTurnCitation.tokenized_content_id).where(
            ConversationTurnCitation.tenant_id == tenant_id,
            ConversationTurnCitation.turn_id == turn_id,
            ConversationTurnCitation.tokenized_content_id.in_(linked),
        ).order_by(ConversationTurnCitation.ordinal)
        ids = list(db.scalars(cited).all())
        if ids:
            return ids[:20]
    return list(db.scalars(linked.order_by(CustomerRecordLink.created_at.desc()).limit(20)).all())


def _generate_protected_draft(
    *,
    customer: Customer,
    rows: list[TokenizedContent],
    instruction: str,
    signature: str,
    channel: str,
) -> tuple[GeneratedOutreachDraft, str]:
    if not rows:
        raise ValueError("outreach_evidence_required")
    evidence = "\n\n".join(
        f"[SOURCE-{index}]\n{row.summary or row.content_text}"
        for index, row in enumerate(rows, 1)
    )
    name = customer.primary_name_token or "Customer"
    context = f"Customer: {name}\n\n{evidence}\n\nUser instruction: {instruction}"
    if contains_known_pii(context):
        raise ValueError("outreach_generation_context_not_protected")
    medium = "Telegram message" if channel == "telegram" else "customer email"
    channel_instruction = (
        "Write a concise chat message with short paragraphs. Do not refer to an email or subject "
        "line. Set the JSON subject to exactly 'Telegram response'. "
        if channel == "telegram"
        else "Write a professional email with a clear subject and body. "
    )
    system = (
        f"Draft a professional {medium} using only the supplied protected evidence. "
        f"{channel_instruction}"
        "Do not infer hidden token values, invent facts, promise an unconfirmed outcome, or "
        "include citation markers in the response. Contact details in the evidence belong to the "
        "customer unless the evidence explicitly says otherwise. Never tell the customer to "
        "contact our company using their own phone number or email address. Do not repeat a "
        "customer contact detail unless the user explicitly asks to confirm it. Do not add a "
        "signature or placeholder fields; the backend adds the configured sender signature. "
        "Return only JSON matching this schema: "
        f"{GeneratedOutreachDraft.model_json_schema()}"
    )
    settings = get_settings()
    mode = "offline-demo"
    if settings.morpheus_api_key:
        response = morpheus_chat(
            [{"role": "system", "content": system}, {"role": "user", "content": context}],
            temperature=0.2,
        )
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.strip())
        draft = GeneratedOutreachDraft.model_validate_json(cleaned)
        mode = "morpheus"
    elif settings.allow_offline_demo:
        draft = GeneratedOutreachDraft(
            subject="Follow-up on your request",
            body=(
                f"Hello {name},\n\nThank you for contacting us. We have reviewed your request "
                "and our team will follow up using the information provided.\n\n"
                "Kind regards,\nFinBrain"
            ),
        )
    else:
        raise RuntimeError("Morpheus is required for outreach draft generation")
    unsigned_body = re.split(
        r"\n\s*(?:best|kind|warm) regards,?\s*(?:\n|$)",
        draft.body,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].rstrip()
    unsigned_body = _remove_customer_contact_misuse(unsigned_body)
    if not unsigned_body:
        raise ValueError("generated_outreach_body_empty_after_safety_review")
    draft = draft.model_copy(
        update={
            "subject": "Telegram response" if channel == "telegram" else draft.subject,
            "body": f"{unsigned_body}\n\nBest regards,\n{signature}",
        }
    )
    serialized = draft.model_dump_json()
    if contains_known_pii(serialized):
        raise ValueError("generated_outreach_contains_sensitive_data")
    allowed_tokens = set(TOKEN_PATTERN.findall(f"{context}\n{signature}"))
    if unknown_tokens(serialized, allowed_tokens):
        raise ValueError("generated_outreach_contains_unknown_token")
    return draft, mode


def generate_action(
    db: Session,
    *,
    tenant_id: str,
    customer_id: int,
    endpoint_id: int,
    turn_id: int | None,
    instruction: str,
    idempotency_key: str,
    created_by_user_id: str,
    actor_role: str,
    actor_ref: str,
) -> tuple[OutreachActionResponse, str]:
    customer = db.get(Customer, customer_id)
    if customer is None or customer.tenant_id != tenant_id:
        raise LookupError("customer_not_found")
    endpoint = _validate_outreach_endpoint(
        db,
        tenant_id=tenant_id,
        customer_id=customer_id,
        endpoint_id=endpoint_id,
        require_verified=True,
    )
    protected_instruction, instruction_entries = protect_text(
        instruction,
        f"outreach-instruction:{idempotency_key}",
        tenant_id,
        db,
    )
    settings = get_settings()
    signature_name = settings.email_outreach_signature_name.strip() or "FinBrain Team"
    signature_title = settings.email_outreach_signature_title.strip()
    signature_organization = settings.email_outreach_signature_organization.strip()
    signature_lines = [
        protect_scalar(
            db,
            entity_type="ORG",
            value=signature_name,
            source_record_id=f"outreach-signature-name:{idempotency_key}",
            tenant_id=tenant_id,
        ),
        signature_title,
    ]
    if signature_organization and signature_organization != signature_name:
        signature_lines.append(
            protect_scalar(
                db,
                entity_type="ORG",
                value=signature_organization,
                source_record_id=f"outreach-signature-organization:{idempotency_key}",
                tenant_id=tenant_id,
            )
        )
    protected_signature = "\n".join(line for line in signature_lines if line)
    persist_vault_entries(db, instruction_entries)
    evidence_ids = _turn_evidence_ids(
        db, tenant_id=tenant_id, customer_id=customer_id, turn_id=turn_id
    )
    rows_by_id = {
        row.id: row
        for row in db.scalars(
            select(TokenizedContent).where(
                TokenizedContent.tenant_id == tenant_id,
                TokenizedContent.id.in_(evidence_ids),
                TokenizedContent.processing_status == "ready",
            )
        ).all()
    }
    rows = [rows_by_id[row_id] for row_id in evidence_ids if row_id in rows_by_id]
    draft, mode = _generate_protected_draft(
        customer=customer,
        rows=rows,
        instruction=protected_instruction,
        signature=protected_signature,
        channel=endpoint.channel,
    )
    action = create_action(
        db,
        tenant_id=tenant_id,
        customer_id=customer_id,
        endpoint_id=endpoint_id,
        subject=draft.subject,
        body=draft.body,
        idempotency_key=idempotency_key,
        evidence_ids=evidence_ids,
        created_by_user_id=created_by_user_id,
        actor_role=actor_role,
        actor_ref=actor_ref,
    )
    return action, mode


def update_draft(
    db: Session,
    action_id: str,
    *,
    tenant_id: str,
    subject: str | None,
    body: str,
    actor_role: str,
    actor_ref: str,
) -> OutreachActionResponse:
    row = db.get(OutreachAction, action_id)
    if row is None or row.tenant_id != tenant_id:
        raise LookupError("outreach_action_not_found")
    if row.status != "draft":
        raise ValueError("only_draft_outreach_can_be_edited")
    subject_entries = []
    subject_protected = row.protected_subject
    if row.channel == "email":
        if subject is None or not subject.strip():
            raise ValueError("email_subject_required")
        subject_protected, subject_entries = protect_text(
            subject, f"outreach-subject:{action_id}:edit", tenant_id, db
        )
    body_protected, body_entries = protect_text(
        body, f"outreach-body:{action_id}:edit", tenant_id, db
    )
    persist_vault_entries(db, [*subject_entries, *body_entries])
    row.protected_subject = subject_protected
    row.protected_body = body_protected
    write_workflow_event(
        db,
        event_type="outreach_draft_edited",
        actor_role=actor_role,
        actor_ref=actor_ref,
        resource_type="outreach_action",
        resource_id=row.id,
        tenant_id=tenant_id,
        event_payload={"customer_id": row.customer_id, "status": row.status},
    )
    db.commit()
    return _response(db, row)


_TRANSITIONS = {
    "submit": ("draft", "pending_approval"),
    "approve": ("pending_approval", "approved"),
    "reject": ("pending_approval", "rejected"),
    "cancel": ("draft", "cancelled"),
}


def transition_action(
    db: Session, action_id: str, operation: str, *, tenant_id: str,
    role: UserRole, user_id: str, actor_ref: str,
) -> OutreachActionResponse:
    expected, target = _TRANSITIONS.get(operation, (None, None))
    if expected is None:
        raise ValueError("unsupported_outreach_transition")
    if operation in {"approve", "reject"} and role is not UserRole.OWNER_DIRECTOR:
        raise PermissionError("owner_director_required")
    row = db.get(OutreachAction, action_id)
    if row is None or row.tenant_id != tenant_id:
        raise LookupError("outreach_action_not_found")
    if operation in {"submit", "approve"}:
        _validate_outreach_endpoint(
            db,
            tenant_id=tenant_id,
            customer_id=row.customer_id,
            endpoint_id=row.customer_endpoint_id,
            require_verified=True,
        )
        customer = db.get(Customer, row.customer_id)
        if customer is None or customer.profile_status != "confirmed":
            raise ValueError("confirmed_customer_required")
        if customer.identity_review_status != "clear":
            raise ValueError("customer_identity_review_required")
    values = {"status": target, "updated_at": datetime.now(UTC)}
    if operation == "approve":
        values.update({"approved_by_user_id": user_id, "approved_at": datetime.now(UTC)})
    changed = db.execute(update(OutreachAction).where(
        OutreachAction.id == action_id, OutreachAction.tenant_id == tenant_id,
        OutreachAction.status == expected,
    ).values(**values)).rowcount
    if changed != 1:
        db.rollback()
        raise ValueError(f"cannot_{operation}_outreach_from_{row.status}")
    write_workflow_event(
        db, event_type=f"outreach_{target}", actor_role=role.value,
        actor_ref=actor_ref, resource_type="outreach_action", resource_id=action_id,
        tenant_id=tenant_id, event_payload={"previous_status": expected, "status": target},
    )
    db.commit()
    return _response(db, db.get(OutreachAction, action_id))


def endpoint_mask(db: Session, row: CustomerEndpoint) -> str:
    registry = db.get(ProtectedTokenRegistry, row.endpoint_token)
    return registry.masked_value if registry else "*****@*******.***"
