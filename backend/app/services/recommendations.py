import hashlib
import hmac
import json
import re
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Conversation,
    ConversationTurn,
    ConversationTurnCitation,
    ProcessRecommendation,
    RecommendationDecision,
    RecommendationEvidence,
    TokenizedContent,
)
from app.schemas import (
    CustomerIntelligenceBrief,
    ProcessAnalysisRequest,
    RecommendationDraft,
    RecommendationEvidenceResponse,
    RecommendationResponse,
    UserRole,
)
from app.security.detect import contains_known_pii, detect_spans
from app.security.detokenize import hash_query
from app.security.tokenize import persist_vault_entries, tokenize_record
from app.services.morpheus import morpheus_chat
from app.services.reasoning import TOKEN_PATTERN, unknown_tokens
from app.services.workflow_audit import write_workflow_event


def _actor_ref(role: UserRole) -> str:
    return hmac.new(
        get_settings().token_root_secret.encode(),
        f"demo-recommendation-actor:{role.value}".encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


def _candidate_rows(
    db: Session, request: ProcessAnalysisRequest, window_start: datetime, tenant_id: str
) -> list[TokenizedContent]:
    return list(
        db.scalars(
            select(TokenizedContent)
            .where(
                TokenizedContent.processing_status == "ready",
                TokenizedContent.tenant_id == tenant_id,
                TokenizedContent.created_at >= window_start,
                TokenizedContent.source_system.in_(request.source_systems),
                TokenizedContent.structured_summary.is_not(None),
            )
            .order_by(TokenizedContent.created_at.desc())
            .limit(100)
        ).all()
    )


def _select_pattern(
    rows: list[TokenizedContent], minimum_evidence: int
) -> tuple[str, list[TokenizedContent]]:
    groups: dict[str, list[TokenizedContent]] = defaultdict(list)
    for row in rows:
        summary = row.structured_summary or {}
        category = str(summary.get("category") or "general_record")
        if summary.get("action_required"):
            groups[category].append(row)
    eligible = [item for item in groups.items() if len(item[1]) >= minimum_evidence]
    if not eligible:
        raise ValueError("insufficient_recurring_evidence")
    eligible.sort(
        key=lambda item: (len({row.source_system for row in item[1]}), len(item[1])),
        reverse=True,
    )
    category, evidence = eligible[0]
    return category, evidence[:20]


def _evidence_context(rows: list[TokenizedContent]) -> tuple[str, set[str]]:
    blocks: list[str] = []
    identifiers: set[str] = set()
    for index, row in enumerate(rows, 1):
        identifier = f"EVIDENCE-{index}"
        identifiers.add(identifier)
        blocks.append(
            f"[{identifier}]\nSystem: {row.source_system}\nType: {row.record_type or 'record'}"
            f"\nProtected summary: {row.summary or row.content_text[:500]}"
        )
    return "\n\n".join(blocks), identifiers


def _offline_draft(category: str, evidence_ids: list[str]) -> RecommendationDraft:
    readable = category.replace("_", " ")
    return RecommendationDraft(
        title=f"Standardize the {readable} workflow",
        problem_statement=(
            f"Multiple protected records show a recurring {readable} issue requiring attention."
        ),
        recommendation=(
            "Introduce a shared intake checklist, a named process owner, and a daily review queue "
            "for unresolved items."
        ),
        expected_benefit=(
            "Reduce repeated follow-up and shorten the time to resolve customer issues."
        ),
        suggested_owner="Finance Operations",
        success_metric="Reduce average resolution time by 50% within 30 days.",
        category=category,
        priority="medium",
        confidence=min(0.95, 0.55 + len(evidence_ids) * 0.08),
        evidence_ids=evidence_ids,
    )


def _generate_draft(
    category: str,
    context: str,
    evidence_ids: set[str],
    minimum_evidence: int,
) -> tuple[RecommendationDraft, str]:
    settings = get_settings()
    instruction = (
        "Generate one practical process recommendation from protected evidence. Never infer hidden "
        "token values. Return only JSON matching this schema: "
        f"{RecommendationDraft.model_json_schema()}. evidence_ids may contain only supplied IDs."
    )
    if settings.morpheus_api_key:
        try:
            response = morpheus_chat(
                [
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": f"Category: {category}\n\n{context}"},
                ]
            )
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.strip())
            draft = RecommendationDraft.model_validate_json(cleaned)
            _validate_draft(
                draft,
                context=context,
                evidence_ids=evidence_ids,
                minimum_evidence=minimum_evidence,
            )
            return draft, "morpheus"
        except Exception:
            if not settings.allow_offline_demo:
                raise
    if not settings.allow_offline_demo:
        raise RuntimeError("Morpheus is required for process recommendation generation")
    draft = _offline_draft(category, sorted(evidence_ids))
    _validate_draft(
        draft,
        context=context,
        evidence_ids=evidence_ids,
        minimum_evidence=minimum_evidence,
    )
    return draft, "offline-demo"


def _validate_draft(
    draft: RecommendationDraft,
    *,
    context: str,
    evidence_ids: set[str],
    minimum_evidence: int,
) -> None:
    if set(draft.evidence_ids) - evidence_ids:
        raise ValueError("Recommendation contains unknown evidence identifiers")
    if len(set(draft.evidence_ids)) < minimum_evidence:
        raise ValueError("Recommendation does not retain the required evidence count")
    serialized = draft.model_dump_json()
    if contains_known_pii(serialized):
        raise ValueError("Recommendation contains recognizable sensitive data")
    allowed_tokens = set(TOKEN_PATTERN.findall(context))
    if unknown_tokens(serialized, allowed_tokens):
        raise ValueError("Recommendation contains unknown protected tokens")


def _fingerprint(category: str, rows: list[TokenizedContent]) -> str:
    payload = json.dumps(
        {"category": category, "records": sorted(row.source_record_id for row in rows)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hmac.new(
        get_settings().token_root_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()


def analyze_processes(
    db: Session,
    request: ProcessAnalysisRequest,
    *,
    role: UserRole,
    tenant_id: str,
    actor_ref: str | None = None,
    created_by_user_id: str | None = None,
) -> RecommendationResponse:
    if role is not UserRole.OWNER_DIRECTOR:
        raise PermissionError("Owner/director role required")
    window_end = datetime.now(UTC)
    window_start = window_end - timedelta(days=request.window_days)
    category, candidate_rows = _select_pattern(
        _candidate_rows(db, request, window_start, tenant_id), request.minimum_evidence
    )
    context, evidence_ids = _evidence_context(candidate_rows)
    draft, mode = _generate_draft(
        category, context, evidence_ids, request.minimum_evidence
    )
    selected = [
        row
        for index, row in enumerate(candidate_rows, 1)
        if f"EVIDENCE-{index}" in draft.evidence_ids
    ]
    fingerprint = _fingerprint(category, selected)
    existing = db.scalar(
        select(ProcessRecommendation).where(
            ProcessRecommendation.fingerprint == fingerprint,
            ProcessRecommendation.tenant_id == tenant_id,
        )
    )
    if existing:
        return recommendation_response(db, existing)
    row = ProcessRecommendation(
        tenant_id=tenant_id,
        fingerprint=fingerprint,
        title=draft.title,
        problem_statement=draft.problem_statement,
        recommendation=draft.recommendation,
        expected_benefit=draft.expected_benefit,
        suggested_owner=draft.suggested_owner,
        success_metric=draft.success_metric,
        category=draft.category,
        priority=draft.priority.value,
        confidence=draft.confidence,
        status="proposed",
        analysis_window_start=window_start,
        analysis_window_end=window_end,
        record_count=len(selected),
        source_systems=sorted({item.source_system for item in selected}),
        enrichment_mode=mode,
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    db.flush()
    for index, item in enumerate(candidate_rows, 1):
        identifier = f"EVIDENCE-{index}"
        if identifier not in draft.evidence_ids:
            continue
        db.add(
            RecommendationEvidence(
                tenant_id=tenant_id,
                recommendation_id=row.id,
                tokenized_content_id=item.id,
                evidence_excerpt=(item.summary or item.content_text)[:1_000],
                relevance_reason=f"Supports the recurring {category.replace('_', ' ')} pattern.",
            )
        )
    write_workflow_event(
        db,
        event_type="recommendation_generated",
        actor_role=role.value,
        actor_ref=actor_ref or _actor_ref(role),
        resource_type="process_recommendation",
        resource_id=str(row.id),
        tenant_id=tenant_id,
        event_payload={
            "category": row.category,
            "evidence_count": row.record_count,
            "source_systems": row.source_systems,
            "status": row.status,
        },
    )
    db.commit()
    return recommendation_response(db, row)


def recommendation_response(
    db: Session, recommendation: ProcessRecommendation
) -> RecommendationResponse:
    evidence_rows = db.execute(
        select(RecommendationEvidence, TokenizedContent)
        .join(TokenizedContent, TokenizedContent.id == RecommendationEvidence.tokenized_content_id)
        .where(RecommendationEvidence.recommendation_id == recommendation.id)
        .order_by(RecommendationEvidence.id)
    ).all()
    return RecommendationResponse(
        id=recommendation.id,
        title=recommendation.title,
        problem_statement=recommendation.problem_statement,
        recommendation=recommendation.recommendation,
        expected_benefit=recommendation.expected_benefit,
        suggested_owner=recommendation.suggested_owner,
        success_metric=recommendation.success_metric,
        category=recommendation.category,
        priority=recommendation.priority,
        confidence=recommendation.confidence,
        status=recommendation.status,
        analysis_window_start=recommendation.analysis_window_start,
        analysis_window_end=recommendation.analysis_window_end,
        record_count=recommendation.record_count,
        source_systems=recommendation.source_systems,
        enrichment_mode=recommendation.enrichment_mode,
        origin_type=recommendation.origin_type,
        origin_turn_id=recommendation.origin_turn_id,
        origin_query_hash=recommendation.origin_query_hash,
        evidence=[
            RecommendationEvidenceResponse(
                citation_id=f"EVIDENCE-{index}",
                source_record_id=content.source_record_id,
                source_system=content.source_system,
                record_type=content.record_type,
                occurred_at=content.occurred_at,
                evidence_excerpt=evidence.evidence_excerpt,
                relevance_reason=evidence.relevance_reason,
            )
            for index, (evidence, content) in enumerate(evidence_rows, 1)
        ],
        created_at=recommendation.created_at,
        updated_at=recommendation.updated_at,
    )


def list_recommendations(db: Session, tenant_id: str) -> list[RecommendationResponse]:
    rows = db.scalars(
        select(ProcessRecommendation)
        .where(ProcessRecommendation.tenant_id == tenant_id)
        .order_by(ProcessRecommendation.created_at.desc())
    ).all()
    return [recommendation_response(db, row) for row in rows]


def create_recommendation_from_turn(
    db: Session,
    turn_id: int,
    *,
    role: UserRole,
    tenant_id: str,
    action_id: str,
    suggested_owner: str | None = None,
    actor_ref: str | None = None,
    created_by_user_id: str | None = None,
) -> RecommendationResponse:
    if role not in {UserRole.FINANCE_OPS, UserRole.OWNER_DIRECTOR}:
        raise PermissionError("Finance or owner/director role required")
    turn = db.get(ConversationTurn, turn_id)
    if turn is None or turn.tenant_id != tenant_id:
        raise LookupError("Query turn not found")
    conversation = db.get(Conversation, turn.conversation_id)
    stale_owner = (
        created_by_user_id is not None
        and conversation is not None
        and conversation.created_by_user_id != created_by_user_id
    )
    if conversation is None or conversation.tenant_id != tenant_id or stale_owner:
        raise LookupError("Query turn not found")
    if turn.protected_brief is None:
        raise ValueError("The query turn has no persisted intelligence brief")
    brief = CustomerIntelligenceBrief.model_validate(turn.protected_brief)
    action = brief.recommended_action
    verification_claim = None
    if action_id.startswith("verification-gap:"):
        claim_id = action_id.removeprefix("verification-gap:")
        verification_claim = next(
            (claim for claim in brief.missing_information if claim.id == claim_id),
            None,
        )
        if verification_claim is None:
            raise ValueError("Unknown verification gap")
        action_citation_ids = verification_claim.citation_ids
        origin_type = "verification_gap"
        action_title = "Verify missing information before approval"
        action_rationale = verification_claim.statement
        action_owner = "Finance Operations"
        action_priority = "medium"
        success_metric = "Close or explicitly document the cited verification gap before approval."
    else:
        if action is None or action.id != action_id:
            raise ValueError("Unknown intelligence action")
        action_citation_ids = action.citation_ids
        origin_type = "query_brief"
        action_title = action.title
        action_rationale = action.rationale
        action_owner = action.suggested_owner
        action_priority = action.priority.value
        success_metric = "Reduce unresolved approval delays by 50% within 30 days."
    if suggested_owner and contains_known_pii(suggested_owner):
        raise ValueError("Suggested owner contains unsupported sensitive data")
    citation_rows = db.execute(
        select(ConversationTurnCitation, TokenizedContent)
        .join(
            TokenizedContent,
            ConversationTurnCitation.tokenized_content_id == TokenizedContent.id,
        )
        .where(ConversationTurnCitation.turn_id == turn.id)
        .order_by(ConversationTurnCitation.ordinal)
    ).all()
    rows_by_citation = {
        f"SOURCE-{mapping.ordinal}": content for mapping, content in citation_rows
    }
    unknown_citations = set(action_citation_ids) - set(rows_by_citation)
    if unknown_citations:
        raise ValueError("The intelligence action cites evidence outside the query turn")
    rows = [rows_by_citation[citation_id] for citation_id in action_citation_ids]
    if not rows:
        raise ValueError("The query turn has no cited evidence")
    category = "verification_gap" if verification_claim else "query_followup"
    fingerprint = _fingerprint(f"{category}:{turn.id}:{action_id}", rows)
    existing = db.scalar(
        select(ProcessRecommendation).where(
            ProcessRecommendation.fingerprint == fingerprint,
            ProcessRecommendation.tenant_id == tenant_id,
        )
    )
    if existing:
        return recommendation_response(db, existing)
    now = datetime.now(UTC)
    recommendation = ProcessRecommendation(
        tenant_id=tenant_id,
        fingerprint=fingerprint,
        title=action_title,
        problem_statement=brief.executive_summary[:2_000],
        recommendation=action_rationale,
        expected_benefit=(
            "Reduce repeated follow-up and make responsibility visible before customer issues age."
        ),
        suggested_owner=suggested_owner or action_owner,
        success_metric=success_metric,
        category=category,
        priority=action_priority,
        confidence=min(0.95, 0.6 + len(rows) * 0.05),
        status="proposed",
        analysis_window_start=turn.created_at,
        analysis_window_end=now,
        record_count=len(rows),
        source_systems=sorted({row.source_system for row in rows}),
        enrichment_mode=turn.reasoning_mode,
        origin_type=origin_type,
        origin_turn_id=turn.id,
        origin_query_hash=hash_query(turn.protected_question),
        created_by_user_id=created_by_user_id,
    )
    db.add(recommendation)
    db.flush()
    for row in rows:
        db.add(
            RecommendationEvidence(
                tenant_id=tenant_id,
                recommendation_id=recommendation.id,
                tokenized_content_id=row.id,
                evidence_excerpt=(row.summary or row.content_text)[:1_000],
                relevance_reason="Cited by the originating customer-intelligence answer.",
            )
        )
    write_workflow_event(
        db,
        event_type="recommendation_created_from_query",
        actor_role=role.value,
        actor_ref=actor_ref or _actor_ref(role),
        resource_type="process_recommendation",
        resource_id=str(recommendation.id),
        tenant_id=tenant_id,
        event_payload={
            "turn_id": turn.id,
            "origin_type": recommendation.origin_type,
            "origin_query_hash": recommendation.origin_query_hash,
            "evidence_count": len(rows),
            "source_systems": recommendation.source_systems,
            "status": recommendation.status,
        },
    )
    db.commit()
    return recommendation_response(db, recommendation)


def decide_recommendation(
    db: Session,
    recommendation_id: int,
    *,
    decision: str,
    role: UserRole,
    tenant_id: str,
    comment: str,
    actor_ref: str | None = None,
) -> RecommendationResponse:
    if role is not UserRole.OWNER_DIRECTOR:
        raise PermissionError("Owner/director role required")
    row = db.get(ProcessRecommendation, recommendation_id)
    if row is None or row.tenant_id != tenant_id:
        raise LookupError("Recommendation not found")
    transitions = {
        ("proposed", "approved"),
        ("proposed", "rejected"),
        ("approved", "implemented"),
    }
    if (row.status, decision) not in transitions:
        raise ValueError("Invalid recommendation status transition")
    protected_comment = None
    if comment.strip():
        source_id = f"decision:{uuid.uuid4()}"
        protected_comment, entries = tokenize_record(
            comment.strip(), detect_spans(comment.strip()), source_id, tenant_id, db=db
        )
        if contains_known_pii(protected_comment):
            raise ValueError("Decision comment contains unsupported sensitive data")
        persist_vault_entries(db, entries)
    row.status = decision
    resolved_actor_ref = actor_ref or _actor_ref(role)
    db.add(
        RecommendationDecision(
            tenant_id=tenant_id,
            recommendation_id=row.id,
            decision=decision,
            actor_role=role.value,
            actor_ref=resolved_actor_ref,
            protected_comment=protected_comment,
        )
    )
    write_workflow_event(
        db,
        event_type=f"recommendation_{decision}",
        actor_role=role.value,
        actor_ref=resolved_actor_ref,
        resource_type="process_recommendation",
        resource_id=str(row.id),
        tenant_id=tenant_id,
        event_payload={"status": decision, "has_comment": bool(protected_comment)},
    )
    db.commit()
    return recommendation_response(db, row)
