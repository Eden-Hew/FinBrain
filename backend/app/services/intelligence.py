import json
import logging
import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import get_settings
from app.schemas import (
    CustomerIntelligenceBrief,
    IntelligenceAction,
    IntelligenceClaim,
    IntelligenceTimelineEvent,
    SummaryPriority,
)
from app.security.detect import contains_known_pii
from app.security.detokenize import (
    TOKEN_PATTERN,
    DetokenizationTrace,
    detokenize_response_with_trace,
)
from app.services.morpheus import morpheus_chat
from app.services.retrieval import RetrievalHit

logger = logging.getLogger(__name__)

RISK_PATTERN = re.compile(
    r"\b(?:overdue|delay(?:ed|s)?|escalat(?:e|ed|ion)|unresolved|pending|blocked|risk)\b",
    re.IGNORECASE,
)
MISSING_PATTERN = re.compile(
    r"\b(?:no (?:assigned )?(?:owner|manager)|without (?:an )?owner|missing|unassigned)\b",
    re.IGNORECASE,
)
APPROVAL_PATTERN = re.compile(r"\b(?:approval|invoice|payment)\b", re.IGNORECASE)
STOP_WORDS = {
    "and",
    "are",
    "being",
    "do",
    "for",
    "from",
    "how",
    "is",
    "it",
    "next",
    "should",
    "the",
    "this",
    "to",
    "we",
    "what",
    "why",
}


def _compact(value: str, limit: int = 420) -> str:
    text = " ".join(value.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _freshness(hit: RetrievalHit, now: datetime | None = None) -> str:
    if hit.occurred_at is None:
        return "undated"
    current = now or datetime.now(UTC)
    occurred = (
        hit.occurred_at.replace(tzinfo=UTC)
        if hit.occurred_at.tzinfo is None
        else hit.occurred_at.astimezone(UTC)
    )
    age_days = max(0, (current - occurred).days)
    if age_days <= 30:
        return "current"
    if age_days <= 90:
        return "aging"
    return "stale"


def citation_freshness(hit: RetrievalHit) -> tuple[str, int | None]:
    if hit.occurred_at is None:
        return "undated", None
    occurred = (
        hit.occurred_at.replace(tzinfo=UTC)
        if hit.occurred_at.tzinfo is None
        else hit.occurred_at.astimezone(UTC)
    )
    return _freshness(hit), max(0, (datetime.now(UTC) - occurred).days)


def _relevance_score(question: str, hit: RetrievalHit) -> int:
    """Keep the brief focused even when offline retrieval returns a broad corpus."""
    text = f"{hit.protected_summary} {hit.protected_excerpt}".lower()
    terms = {
        term
        for term in re.findall(r"[a-z0-9_]+", question.lower())
        if len(term) >= 4 and term not in STOP_WORDS
    }
    score = sum(2 for term in terms if term in text)
    if "approval" in question.lower() and "payment_approval_delay" in text:
        score += 10
    if "approval" in question.lower() and "approval" in text:
        score += 4
    if "delay" in question.lower() and RISK_PATTERN.search(text):
        score += 3
    if MISSING_PATTERN.search(text):
        score += 2
    return score


def build_protected_brief(
    *,
    question: str,
    protected_answer: str,
    hits: list[RetrievalHit],
    cited_ids: set[str],
    insufficient_evidence: bool,
) -> CustomerIntelligenceBrief | None:
    if not hits and not insufficient_evidence:
        return None
    if insufficient_evidence:
        return CustomerIntelligenceBrief(
            subject_label="Available customer intelligence",
            status="insufficient_evidence",
            executive_summary=protected_answer,
            missing_information=[
                IntelligenceClaim(
                    id="claim-1",
                    statement=(
                        "FinBrain could not find enough protected evidence to support a decision."
                    ),
                    citation_ids=[],
                    relation="missing",
                )
            ],
        )

    claims: list[IntelligenceClaim] = []
    timeline: list[IntelligenceTimelineEvent] = []
    risks: list[IntelligenceClaim] = []
    missing: list[IntelligenceClaim] = []
    open_commitments: list[IntelligenceClaim] = []

    candidates = [
        (index, hit)
        for index, hit in enumerate(hits, 1)
        if f"SOURCE-{index}" in cited_ids
    ]
    ranked = sorted(
        candidates,
        key=lambda item: (_relevance_score(question, item[1]), item[1].similarity),
        reverse=True,
    )
    focused = [item for item in ranked if _relevance_score(question, item[1]) > 0]
    selected = (focused or ranked)[:5]
    for claim_index, (source_index, hit) in enumerate(selected, 1):
        citation_id = f"SOURCE-{source_index}"
        source_text = hit.protected_summary or hit.protected_excerpt
        statement = _compact(source_text)
        freshness = _freshness(hit)
        relation = "stale" if freshness == "stale" else "supporting"
        claim = IntelligenceClaim(
            id=f"claim-{claim_index}",
            statement=statement,
            citation_ids=[citation_id],
            relation=relation,
        )
        claims.append(claim)
        if hit.occurred_at is not None:
            timeline.append(
                IntelligenceTimelineEvent(
                    occurred_at=hit.occurred_at,
                    label=f"{hit.source_system.replace('_', ' ').title()} evidence",
                    detail=statement,
                    citation_ids=[citation_id],
                )
            )
        if RISK_PATTERN.search(source_text):
            risks.append(claim.model_copy(deep=True))
            open_commitments.append(claim.model_copy(deep=True))
        if MISSING_PATTERN.search(source_text):
            missing.append(
                claim.model_copy(update={"relation": "missing"}, deep=True)
            )

    combined = f"{question}\n{protected_answer}\n" + "\n".join(
        claim.statement for claim in claims
    )
    status = "at_risk" if risks else "needs_attention"
    subject = (
        "Payment approval intelligence"
        if APPROVAL_PATTERN.search(combined)
        else "Cross-source customer intelligence"
    )
    cited = [citation for claim in claims for citation in claim.citation_ids]
    action = IntelligenceAction(
        title=(
            "Assign a named approval owner and review the unresolved queue"
            if APPROVAL_PATTERN.search(combined)
            else "Assign an owner to resolve the cited customer issues"
        ),
        rationale=(
            "The cited protected records show repeated action-required work across the "
            "available sources."
        ),
        suggested_owner="Finance Operations",
        priority=SummaryPriority.HIGH if risks else SummaryPriority.MEDIUM,
        citation_ids=cited[:20],
    )
    executive_summary = protected_answer
    if APPROVAL_PATTERN.search(combined) and claims:
        missing_count = len(missing)
        executive_summary = (
            f"{len(claims)} cited records show payment-approval work requiring attention. "
            + (
                f"{missing_count} of those records explicitly identify a missing or "
                "unassigned owner. "
                if missing_count
                else ""
            )
            + "The evidence supports assigning a named owner and reviewing the unresolved "
            "queue daily."
        )

    return CustomerIntelligenceBrief(
        subject_label=subject,
        status=status,
        executive_summary=executive_summary,
        claims=claims,
        timeline=sorted(
            timeline,
            key=lambda event: event.occurred_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        ),
        open_commitments=open_commitments[:3],
        risks=risks[:3],
        missing_information=missing[:3],
        recommended_action=action,
    )


def generate_protected_brief(
    *,
    question: str,
    protected_answer: str,
    hits: list[RetrievalHit],
    cited_ids: set[str],
    insufficient_evidence: bool,
    reasoning_mode: str,
) -> CustomerIntelligenceBrief | None:
    """Generate the live structured artifact, with a grounded offline fallback."""
    def fallback() -> CustomerIntelligenceBrief | None:
        return build_protected_brief(
            question=question,
            protected_answer=protected_answer,
            hits=hits,
            cited_ids=cited_ids,
            insufficient_evidence=insufficient_evidence,
        )
    if insufficient_evidence or reasoning_mode not in {"morpheus", "gemini"}:
        return fallback()

    context = "\n\n".join(
        f"[SOURCE-{index}]\n{hit.retrieval_text}"
        for index, hit in enumerate(hits, 1)
        if f"SOURCE-{index}" in cited_ids
    )
    if contains_known_pii(question) or contains_known_pii(context):
        raise ValueError("Refusing to generate a brief from recognizable sensitive data")
    schema = CustomerIntelligenceBrief.model_json_schema()
    instruction = (
        "Return only a CustomerIntelligenceBrief JSON object. Use only supplied SOURCE-n "
        "citations. Every factual claim and timeline event must cite evidence. Use relation "
        "missing only for a stated information gap. Maximums: five claims, five timeline "
        "events, three risks, three missing-information items. Status must be healthy, "
        "needs_attention, at_risk, or insufficient_evidence. Preserve protected tokens "
        "exactly and never invent people, amounts, contacts, or citations. Follow this JSON "
        f"Schema exactly: {json.dumps(schema, separators=(',', ':'))}"
    )
    prompt = (
        f"Protected evidence:\n{context}\n\nProtected question:\n{question}"
        f"\n\nGrounded protected answer:\n{protected_answer}"
    )
    settings = get_settings()
    try:
        if reasoning_mode == "morpheus" and settings.morpheus_api_key:
            response = morpheus_chat(
                [
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": prompt},
                ]
            )
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.strip())
            return CustomerIntelligenceBrief.model_validate_json(cleaned)
        if reasoning_mode == "gemini" and settings.gemini_api_key:
            from google import genai

            response = genai.Client(api_key=settings.gemini_api_key).models.generate_content(
                model=settings.gemini_reasoning_model,
                contents=prompt,
                config={
                    "system_instruction": instruction,
                    "response_mime_type": "application/json",
                    "response_schema": CustomerIntelligenceBrief,
                    "temperature": 0.1,
                },
            )
            return (
                response.parsed
                if isinstance(response.parsed, CustomerIntelligenceBrief)
                else CustomerIntelligenceBrief.model_validate(response.parsed)
                if response.parsed is not None
                else CustomerIntelligenceBrief.model_validate_json(response.text or "")
            )
    except Exception as error:
        logger.warning(
            "intelligence_brief_provider_failed mode=%s error_type=%s",
            reasoning_mode,
            type(error).__name__,
        )
        if not settings.allow_offline_demo:
            raise
    return fallback()


def validate_protected_brief(
    brief: CustomerIntelligenceBrief,
    *,
    allowed_citations: set[str],
    protected_context: str,
) -> None:
    """Validate grounding and privacy before a protected brief is persisted."""
    claims = [
        *brief.claims,
        *brief.open_commitments,
        *brief.risks,
        *brief.missing_information,
    ]
    for claim in claims:
        if claim.relation != "missing" and not claim.citation_ids:
            raise ValueError("Every factual intelligence claim requires a citation")
        if set(claim.citation_ids) - allowed_citations:
            raise ValueError("The intelligence brief contains an unknown citation")
    for event in brief.timeline:
        if not event.citation_ids:
            raise ValueError("Every intelligence timeline event requires a citation")
        if set(event.citation_ids) - allowed_citations:
            raise ValueError("The intelligence brief contains an unknown citation")
    if brief.recommended_action and (
        set(brief.recommended_action.citation_ids) - allowed_citations
    ):
        raise ValueError("The intelligence action contains an unknown citation")
    serialized = brief.model_dump_json()
    if contains_known_pii(serialized):
        raise ValueError("The intelligence brief contains recognizable sensitive data")
    allowed_tokens = set(TOKEN_PATTERN.findall(protected_context))
    returned_tokens = set(TOKEN_PATTERN.findall(serialized))
    if returned_tokens - allowed_tokens:
        raise ValueError("The intelligence brief contains an unknown protected token")


def authorize_brief_with_trace(
    db: Session,
    brief: CustomerIntelligenceBrief | None,
    *,
    role: str,
    query_hash: str,
    actor_ref: str = "legacy",
    turn_ref: str = "unbound",
) -> tuple[CustomerIntelligenceBrief | None, DetokenizationTrace | None]:
    if brief is None:
        return None, None
    trace = detokenize_response_with_trace(
        db,
        brief.model_dump_json(),
        role,
        query_hash,
        actor_ref=actor_ref,
        turn_ref=turn_ref,
    )
    try:
        parsed = json.loads(trace.text, strict=False)
        return CustomerIntelligenceBrief.model_validate(parsed), trace
    except Exception as error:
        logger.warning("Failed to parse detokenized brief JSON; falling back to original: %s", error)
        return brief, trace


def authorize_brief(
    db: Session,
    brief: CustomerIntelligenceBrief | None,
    *,
    role: str,
    query_hash: str,
    actor_ref: str = "legacy",
    turn_ref: str = "unbound",
) -> CustomerIntelligenceBrief | None:
    authorized, _trace = authorize_brief_with_trace(
        db,
        brief,
        role=role,
        query_hash=query_hash,
        actor_ref=actor_ref,
        turn_ref=turn_ref,
    )
    return authorized
