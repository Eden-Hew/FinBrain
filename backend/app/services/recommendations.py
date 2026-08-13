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
    ProcessRecommendation,
    RecommendationDecision,
    RecommendationEvidence,
    TokenizedContent,
    TokenVaultEntry,
)
from app.schemas import (
    ProcessAnalysisRequest,
    RecommendationDraft,
    RecommendationEvidenceResponse,
    RecommendationResponse,
    UserRole,
)
from app.security.detect import contains_known_pii, detect_spans
from app.security.tokenize import tokenize_record
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
    db: Session, request: ProcessAnalysisRequest, window_start: datetime
) -> list[TokenizedContent]:
    return list(
        db.scalars(
            select(TokenizedContent)
            .where(
                TokenizedContent.processing_status == "ready",
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


def analyze_processes(db: Session, request: ProcessAnalysisRequest) -> RecommendationResponse:
    if request.role is not UserRole.OWNER_DIRECTOR:
        raise PermissionError("Owner/director role required")
    window_end = datetime.now(UTC)
    window_start = window_end - timedelta(days=request.window_days)
    category, candidate_rows = _select_pattern(
        _candidate_rows(db, request, window_start), request.minimum_evidence
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
        select(ProcessRecommendation).where(ProcessRecommendation.fingerprint == fingerprint)
    )
    if existing:
        return recommendation_response(db, existing)
    row = ProcessRecommendation(
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
    )
    db.add(row)
    db.flush()
    for index, item in enumerate(candidate_rows, 1):
        identifier = f"EVIDENCE-{index}"
        if identifier not in draft.evidence_ids:
            continue
        db.add(
            RecommendationEvidence(
                recommendation_id=row.id,
                tokenized_content_id=item.id,
                evidence_excerpt=(item.summary or item.content_text)[:1_000],
                relevance_reason=f"Supports the recurring {category.replace('_', ' ')} pattern.",
            )
        )
    write_workflow_event(
        db,
        event_type="recommendation_generated",
        actor_role=request.role.value,
        actor_ref=_actor_ref(request.role),
        resource_type="process_recommendation",
        resource_id=str(row.id),
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


def list_recommendations(db: Session) -> list[RecommendationResponse]:
    rows = db.scalars(
        select(ProcessRecommendation).order_by(ProcessRecommendation.created_at.desc())
    ).all()
    return [recommendation_response(db, row) for row in rows]


def decide_recommendation(
    db: Session,
    recommendation_id: int,
    *,
    decision: str,
    role: UserRole,
    comment: str,
) -> RecommendationResponse:
    if role is not UserRole.OWNER_DIRECTOR:
        raise PermissionError("Owner/director role required")
    row = db.get(ProcessRecommendation, recommendation_id)
    if row is None:
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
            comment.strip(), detect_spans(comment.strip()), source_id
        )
        if contains_known_pii(protected_comment):
            raise ValueError("Decision comment contains unsupported sensitive data")
        for entry in entries:
            if db.get(TokenVaultEntry, entry.token) is None:
                db.add(entry)
    row.status = decision
    actor_ref = _actor_ref(role)
    db.add(
        RecommendationDecision(
            recommendation_id=row.id,
            decision=decision,
            actor_role=role.value,
            actor_ref=actor_ref,
            protected_comment=protected_comment,
        )
    )
    write_workflow_event(
        db,
        event_type=f"recommendation_{decision}",
        actor_role=role.value,
        actor_ref=actor_ref,
        resource_type="process_recommendation",
        resource_id=str(row.id),
        event_payload={"status": decision, "has_comment": bool(protected_comment)},
    )
    db.commit()
    return recommendation_response(db, row)
