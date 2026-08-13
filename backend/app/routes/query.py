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
from app.services.query_planning import QueryIntent, plan_query, source_inventory
from app.services.reasoning import (
    answer_all_query_with_citations,
    structured_record_listing,
    unknown_tokens,
)
from app.services.retrieval import RetrievalHit, list_filtered_hits

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
def query(payload: QueryRequest, db: Session = Depends(get_db)) -> QueryResponse:
    inventory = source_inventory(db)
    plan = plan_query(payload.question, [source for source, _count in inventory])
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
        hits = []
        selected_counts = [
            (source, count)
            for source, count in inventory
            if not plan.source_systems or source in plan.source_systems
        ]
        total = sum(count for _source, count in selected_counts)
        scope = (
            ", ".join(plan.source_systems)
            if plan.source_systems
            else "all source systems"
        )
        cited_answer = CitedAnswer(
            answer=f"{scope}: {total} ready record(s).",
            citations=[],
            insufficient_evidence=total == 0,
        )
        reasoning_mode = "structured-filter"
    elif plan.intent is QueryIntent.LIST_RECORDS:
        hits = list_filtered_hits(
            db, source_systems=list(plan.source_systems), limit=50
        )
        cited_answer = structured_record_listing(hits)
        reasoning_mode = "structured-filter"
    else:
        hits = list_filtered_hits(
            db, source_systems=list(plan.source_systems) or None, limit=None
        )
        cited_answer, reasoning_mode = answer_all_query_with_citations(
            sanitized_question, hits
        )
    raw_answer = cited_answer.answer
    known_tokens = set(db.scalars(select(TokenVaultEntry.token)).all())
    invented = unknown_tokens(raw_answer, known_tokens)
    if invented:
        raise HTTPException(status_code=502, detail="The model returned an unknown protected token")
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
    )
