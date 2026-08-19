from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, require_roles
from app.auth.principal import AuthPrincipal
from app.db import get_db
from app.models import ConversationTurn, ConversationTurnCitation, TokenizedContent
from app.schemas import (
    CitationDetailResponse,
    QueryCitation,
    RoleComparisonRequest,
    RoleComparisonResponse,
    RoleComparisonResult,
    UserRole,
)
from app.security.detokenize import detokenize_response_with_trace, hash_query
from app.services.conversations import get_active_conversation
from app.services.intelligence import citation_freshness
from app.services.retrieval import RetrievalHit

router = APIRouter(prefix="/query-turns", tags=["query-artifacts"])


def _turn(db: Session, turn_id: int, tenant_id: str, user_id: str) -> ConversationTurn:
    turn = db.get(ConversationTurn, turn_id)
    if turn is None or turn.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="query_turn_not_found")
    try:
        get_active_conversation(db, turn.conversation_id, tenant_id, user_id)
    except ValueError as error:
        code = str(error)
        raise HTTPException(
            status_code=410 if code == "conversation_expired" else 404,
            detail=code,
        ) from error
    return turn


def _citation(
    db: Session, turn_id: int, citation_id: str
) -> tuple[ConversationTurnCitation, TokenizedContent]:
    try:
        ordinal = int(citation_id.removeprefix("SOURCE-"))
    except ValueError as error:
        raise HTTPException(status_code=404, detail="citation_not_found") from error
    if citation_id != f"SOURCE-{ordinal}" or ordinal < 1:
        raise HTTPException(status_code=404, detail="citation_not_found")
    pair = db.execute(
        select(ConversationTurnCitation, TokenizedContent)
        .join(
            TokenizedContent,
            TokenizedContent.id == ConversationTurnCitation.tokenized_content_id,
        )
        .where(
            ConversationTurnCitation.turn_id == turn_id,
            ConversationTurnCitation.ordinal == ordinal,
        )
    ).first()
    if pair is None:
        raise HTTPException(status_code=404, detail="citation_not_found")
    return pair


@router.get(
    "/{turn_id}/citations/{citation_id}", response_model=CitationDetailResponse
)
def citation_detail(
    turn_id: int,
    citation_id: str,
    principal: CurrentUser,
    db: Session = Depends(get_db),
) -> CitationDetailResponse:
    turn = _turn(db, turn_id, str(principal.tenant_id), str(principal.user_id))
    _mapping, content = _citation(db, turn.id, citation_id)
    hit = RetrievalHit(
        content_id=content.id,
        source_record_id=content.source_record_id,
        source_system=content.source_system,
        record_type=content.record_type,
        occurred_at=content.occurred_at,
        protected_excerpt=content.content_text,
        protected_summary=content.summary,
        similarity=1.0,
    )
    freshness, age_days = citation_freshness(hit)
    query_hash_value = hash_query(turn.protected_question)
    trace = detokenize_response_with_trace(
        db,
        hit.retrieval_text[:1_000],
        principal.role.value,
        query_hash_value,
        actor_ref=principal.actor_ref,
        turn_ref=str(turn.id),
    )
    if trace.withheld_tokens and trace.restored_tokens:
        explanation = "Some protected values are visible to this role; others remain withheld."
    elif trace.withheld_tokens:
        explanation = "Restricted values remain protected under this role's disclosure policy."
    elif trace.restored_tokens:
        explanation = "Protected values were restored because this role is authorized."
    else:
        explanation = "This evidence contains no protected values requiring restoration."
    return CitationDetailResponse(
        citation=QueryCitation(
            citation_id=citation_id,
            source_record_id=content.source_record_id,
            source_system=content.source_system,
            record_type=content.record_type,
            occurred_at=content.occurred_at,
            protected_excerpt=hit.retrieval_text[:1_000],
            similarity=1.0,
            freshness=freshness,
            age_days=age_days,
            relation="stale" if freshness == "stale" else "supporting",
        ),
        authorized_excerpt=trace.text,
        restored_tokens=trace.restored_tokens,
        withheld_tokens=trace.withheld_tokens,
        access_explanation=explanation,
        query_hash=query_hash_value,
    )


@router.post("/{turn_id}/compare-roles", response_model=RoleComparisonResponse)
def compare_roles(
    turn_id: int,
    payload: RoleComparisonRequest,
    principal: AuthPrincipal = Depends(require_roles(UserRole.COMPLIANCE)),
    db: Session = Depends(get_db),
) -> RoleComparisonResponse:
    if principal.role is not UserRole.COMPLIANCE:
        raise HTTPException(status_code=403, detail="Compliance role required")
    turn = _turn(db, turn_id, str(principal.tenant_id), str(principal.user_id))
    roles = list(dict.fromkeys(payload.comparison_roles))
    query_hash_value = hash_query(turn.protected_question)
    results: list[RoleComparisonResult] = []
    for role in roles:
        trace = detokenize_response_with_trace(
            db,
            turn.protected_answer,
            role.value,
            query_hash_value,
            actor_ref=principal.actor_ref,
            turn_ref=f"{turn.id}:comparison:{role.value}",
        )
        explanations: list[str] = []
        if trace.restored_tokens:
            explanations.append(
                f"{trace.restored_tokens} protected value(s) restored for this policy."
            )
        if trace.withheld_tokens:
            explanations.append(
                f"{trace.withheld_tokens} protected value(s) withheld by this policy."
            )
        if not explanations:
            explanations.append("No protected value changed under this policy.")
        results.append(
            RoleComparisonResult(
                role=role,
                answer=trace.text,
                restored_tokens=trace.restored_tokens,
                withheld_tokens=trace.withheld_tokens,
                policy_explanations=explanations,
            )
        )
    return RoleComparisonResponse(
        turn_id=turn.id,
        query_hash=query_hash_value,
        protected_answer=turn.protected_answer,
        results=results,
    )
