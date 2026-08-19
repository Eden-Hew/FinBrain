import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.config import get_settings
from app.db import get_db
from app.models import ProtectedTokenRegistry, VaultKeyVersion
from app.schemas import CitedAnswer, ExposureReceipt, QueryCitation, QueryRequest, QueryResponse
from app.security.detect import contains_known_pii, detect_spans
from app.security.detokenize import TOKEN_PATTERN, detokenize_response_with_trace, hash_query
from app.security.tokenize import persist_vault_entries, tokenize_record
from app.services.conversations import (
    get_or_create_conversation,
    is_referential_question,
    persist_turn,
    prior_citation_hits,
    protected_history,
)
from app.services.intelligence import (
    authorize_brief_with_trace,
    citation_freshness,
    generate_protected_brief,
    validate_protected_brief,
)
from app.services.query_filters import list_eligible_hits
from app.services.query_planning import QueryIntent, plan_query, source_inventory
from app.services.reasoning import (
    answer_all_query_with_citations,
    structured_record_listing,
    unknown_tokens,
)
from app.services.retrieval import RetrievalHit

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
def query(
    payload: QueryRequest,
    principal: CurrentUser,
    db: Session = Depends(get_db),
) -> QueryResponse:
    inventory = source_inventory(db, str(principal.tenant_id))
    plan = plan_query(
        payload.question,
        [source for source, _count in inventory],
        tenant_id=str(principal.tenant_id),
    )
    try:
        conversation = get_or_create_conversation(
            db, payload.conversation_id, str(principal.tenant_id), str(principal.user_id)
        )
    except ValueError as error:
        code = str(error)
        raise HTTPException(
            status_code=410 if code == "conversation_expired" else 404,
            detail=code,
        ) from error
    history = protected_history(db, conversation.id, str(principal.tenant_id))
    query_id = f"query-{uuid.uuid4()}"
    sanitized_question, query_entries = tokenize_record(
        payload.question, detect_spans(payload.question), query_id, str(principal.tenant_id), db=db
    )
    if contains_known_pii(sanitized_question):
        raise HTTPException(
            status_code=422, detail="The question contains unsupported sensitive data"
        )
    persist_vault_entries(db, query_entries)
    db.commit()

    referential = bool(payload.conversation_id) and is_referential_question(payload.question)
    prior_hits = (
        prior_citation_hits(
            db,
            conversation.id,
            payload.question,
            str(principal.tenant_id),
        )
        if referential
        else None
    )
    if prior_hits is not None:
        prior_ids = [hit.content_id for hit in prior_hits]
        prior_hits = (
            list_eligible_hits(db, plan.filters.with_content_ids(prior_ids)) if prior_ids else []
        )
    # Referential scope is resolved deterministically to current hits above.
    # Do not expose historical SOURCE-n labels to the model after those hits
    # have been remapped to the current turn's SOURCE-n namespace.
    reasoning_question = (
        (
            "FinBrain's deterministic conversation resolver has already selected the "
            "protected evidence supplied with this request as the user's intended referent. "
            "Answer about that selected evidence directly; do not say the referent or its "
            "ordinal is missing merely because the earlier list is not repeated. Use only the "
            "current SOURCE-n citation identifiers.\n\n"
            f"User follow-up: {sanitized_question}"
        )
        if referential
        else f"{history}\n\nCurrent protected question: {sanitized_question}"
        if history
        else sanitized_question
    )

    hits: list[RetrievalHit]
    conversation_context_hits: list[RetrievalHit] | None = None
    if plan.intent is QueryIntent.LIST_SOURCES:
        hits = []
        cited_answer = CitedAnswer(
            answer=(
                "Available ready source systems:\n\n"
                + "\n".join(f"- {source}: {count} record(s)" for source, count in inventory)
            ),
            citations=[],
            insufficient_evidence=not inventory,
        )
        reasoning_mode = "structured-filter"
    elif plan.intent is QueryIntent.COUNT_SOURCES:
        hits = []
        cited_answer = CitedAnswer(
            answer=f"There are {len(inventory)} ready source system(s).",
            citations=[],
            insufficient_evidence=not inventory,
        )
        reasoning_mode = "structured-filter"
    elif plan.intent is QueryIntent.COUNT_RECORDS:
        if referential:
            hits = prior_hits or []
            conversation_context_hits = hits
        else:
            hits = []
            conversation_context_hits = list_eligible_hits(db, plan.filters)
        total = len(conversation_context_hits)
        scope = ", ".join(plan.source_systems) if plan.source_systems else "all source systems"
        cited_answer = CitedAnswer(
            answer=f"{scope}: {total} ready record(s).",
            citations=(
                [f"SOURCE-{index}" for index in range(1, len(hits) + 1)] if referential else []
            ),
            insufficient_evidence=total == 0,
        )
        reasoning_mode = "structured-filter"
    elif plan.intent is QueryIntent.LIST_RECORDS:
        hits = prior_hits or [] if referential else list_eligible_hits(db, plan.filters, limit=50)
        cited_answer = structured_record_listing(hits)
        reasoning_mode = "structured-filter"
    else:
        hits = prior_hits or [] if referential else list_eligible_hits(db, plan.filters)
        cited_answer, reasoning_mode = answer_all_query_with_citations(reasoning_question, hits)
    raw_answer = cited_answer.answer
    known_tokens = set(db.scalars(select(ProtectedTokenRegistry.token)).all())
    invented = unknown_tokens(raw_answer, known_tokens)
    if invented:
        raise HTTPException(status_code=502, detail="The model returned an unknown protected token")
    cited_pairs = [
        (index, hit)
        for index, hit in enumerate(hits, 1)
        if f"SOURCE-{index}" in cited_answer.citations
    ]
    cited_hits = [hit for _index, hit in cited_pairs]
    protected_brief = (
        generate_protected_brief(
            question=sanitized_question,
            protected_answer=raw_answer,
            hits=hits,
            cited_ids=set(cited_answer.citations),
            insufficient_evidence=cited_answer.insufficient_evidence,
            reasoning_mode=reasoning_mode,
        )
        if plan.intent in {QueryIntent.SEMANTIC, QueryIntent.ANALYZE_ALL}
        else None
    )
    if protected_brief is not None:
        validate_protected_brief(
            protected_brief,
            allowed_citations=set(cited_answer.citations),
            protected_context="\n".join(hit.retrieval_text for hit in hits),
        )
    turn = persist_turn(
        db,
        conversation,
        user_role=principal.role.value,
        protected_question=sanitized_question,
        protected_answer=raw_answer,
        protected_brief=(
            protected_brief.model_dump(mode="json") if protected_brief else None
        ),
        query_intent=plan.intent.value,
        source_systems=list(plan.source_systems),
        reasoning_mode=reasoning_mode,
        insufficient_evidence=cited_answer.insufficient_evidence,
        cited_hits=(
            conversation_context_hits
            if conversation_context_hits is not None
            else cited_hits
        ),
        citation_ordinals=(
            None
            if conversation_context_hits is not None
            else [index for index, _hit in cited_pairs]
        ),
    )
    query_hash_value = hash_query(sanitized_question)
    answer_trace = detokenize_response_with_trace(
        db,
        raw_answer,
        principal.role.value,
        query_hash_value,
        actor_ref=principal.actor_ref,
        turn_ref=str(turn.id),
    )
    authorized_brief, brief_trace = authorize_brief_with_trace(
        db,
        protected_brief,
        role=principal.role.value,
        query_hash=query_hash_value,
        actor_ref=principal.actor_ref,
        turn_ref=str(turn.id),
    )
    settings = get_settings()
    reasoning_model = (
        settings.morpheus_model
        if reasoning_mode == "morpheus"
        else settings.gemini_reasoning_model
        if reasoning_mode == "gemini"
        else None
    )
    return QueryResponse(
        answer=answer_trace.text,
        model_answer=raw_answer,
        model_question=sanitized_question,
        query_intent=plan.intent.value,
        sources_used=len(hits),
        mode=reasoning_mode,
        insufficient_evidence=cited_answer.insufficient_evidence,
        citations=[
            QueryCitation(
                citation_id=f"SOURCE-{index}",
                source_record_id=hit.source_record_id,
                source_system=hit.source_system,
                record_type=hit.record_type,
                occurred_at=hit.occurred_at,
                protected_excerpt=hit.retrieval_text[:1_000],
                similarity=hit.similarity,
                freshness=citation_freshness(hit)[0],
                age_days=citation_freshness(hit)[1],
                relation=(
                    "stale" if citation_freshness(hit)[0] == "stale" else "supporting"
                ),
            )
            for index, hit in enumerate(hits, 1)
            if f"SOURCE-{index}" in cited_answer.citations
        ],
        conversation_id=conversation.id,
        turn_id=turn.id,
        intelligence_brief=authorized_brief,
        protected_intelligence_brief=protected_brief,
        exposure_receipt=ExposureReceipt(
            request_id=query_id,
            query_hash=query_hash_value,
            reasoning_mode=reasoning_mode,
            reasoning_model=reasoning_model,
            external_ai_used=reasoning_mode in {"morpheus", "gemini"},
            privacy_preflight_passed=True,
            recognized_sensitive_fields=len(query_entries),
            protected_question_tokens=len(set(TOKEN_PATTERN.findall(sanitized_question))),
            protected_context_tokens=len(
                {
                    token
                    for hit in hits
                    for token in TOKEN_PATTERN.findall(hit.retrieval_text)
                }
            ),
            restored_tokens=(
                brief_trace.restored_tokens if brief_trace else answer_trace.restored_tokens
            ),
            withheld_tokens=(
                brief_trace.withheld_tokens if brief_trace else answer_trace.withheld_tokens
            ),
            active_role=principal.role,
            sources_supplied=len(hits),
            disclosure_session_ref=(
                brief_trace.disclosure_session_ref
                if brief_trace
                else answer_trace.disclosure_session_ref
            ),
            single_use_grants=(
                brief_trace.single_use_grants
                if brief_trace
                else answer_trace.single_use_grants
            ),
            vault_key_version=(
                db.scalar(
                    select(VaultKeyVersion.version)
                    .where(VaultKeyVersion.status == "active")
                    .limit(1)
                )
                or 1
            ),
        ),
    )
