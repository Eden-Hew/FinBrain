import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import TokenVaultEntry
from app.schemas import CitedAnswer, QueryCitation, QueryRequest, QueryResponse
from app.security.detect import contains_known_pii, detect_spans
from app.security.detokenize import detokenize_response, hash_query
from app.security.tokenize import tokenize_record
from app.services.conversations import (
    get_or_create_conversation,
    is_referential_question,
    persist_turn,
    prior_citation_hits,
    protected_history,
)
from app.services.query_filters import count_eligible_records, list_eligible_hits
from app.services.query_planning import QueryIntent, plan_query, source_inventory
from app.services.reasoning import (
    answer_all_query_with_citations,
    structured_record_listing,
    unknown_tokens,
)
from app.services.retrieval import RetrievalHit

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
def query(payload: QueryRequest, db: Session = Depends(get_db)) -> QueryResponse:
    inventory = source_inventory(db)
    plan = plan_query(payload.question, [source for source, _count in inventory])
    try:
        conversation = get_or_create_conversation(db, payload.conversation_id)
    except ValueError as error:
        code = str(error)
        raise HTTPException(
            status_code=410 if code == "conversation_expired" else 404,
            detail=code,
        ) from error
    history = protected_history(db, conversation.id)
    query_id = f"query-{uuid.uuid4()}"
    sanitized_question, query_entries = tokenize_record(
        payload.question, detect_spans(payload.question), query_id
    )
    if contains_known_pii(sanitized_question):
        raise HTTPException(
            status_code=422, detail="The question contains unsupported sensitive data"
        )
    for entry in query_entries:
        if db.get(TokenVaultEntry, entry.token) is None:
            db.add(entry)
    db.commit()

    referential = bool(payload.conversation_id) and is_referential_question(payload.question)
    prior_hits = (
        prior_citation_hits(
            db,
            conversation.id,
            payload.question,
        )
        if referential
        else None
    )
    if prior_hits is not None:
        prior_ids = [hit.content_id for hit in prior_hits]
        prior_hits = (
            list_eligible_hits(db, plan.filters.with_content_ids(prior_ids)) if prior_ids else []
        )
    reasoning_question = (
        f"{history}\n\nCurrent protected question: {sanitized_question}"
        if history
        else sanitized_question
    )

    hits: list[RetrievalHit]
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
        hits = prior_hits or [] if referential else []
        total = len(hits) if referential else count_eligible_records(db, plan.filters)
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
    known_tokens = set(db.scalars(select(TokenVaultEntry.token)).all())
    invented = unknown_tokens(raw_answer, known_tokens)
    if invented:
        raise HTTPException(status_code=502, detail="The model returned an unknown protected token")
    cited_hits = [
        hit for index, hit in enumerate(hits, 1) if f"SOURCE-{index}" in cited_answer.citations
    ]
    turn = persist_turn(
        db,
        conversation,
        user_role=payload.role.value,
        protected_question=sanitized_question,
        protected_answer=raw_answer,
        query_intent=plan.intent.value,
        source_systems=list(plan.source_systems),
        reasoning_mode=reasoning_mode,
        insufficient_evidence=cited_answer.insufficient_evidence,
        cited_hits=cited_hits,
    )
    final_answer = detokenize_response(
        db, raw_answer, payload.role.value, hash_query(payload.question)
    )
    return QueryResponse(
        answer=final_answer,
        model_answer=raw_answer,
        model_question=sanitized_question,
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
            )
            for index, hit in enumerate(hits, 1)
            if f"SOURCE-{index}" in cited_answer.citations
        ],
        conversation_id=conversation.id,
        turn_id=turn.id,
    )
