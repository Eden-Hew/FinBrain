import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import TokenVaultEntry
from app.schemas import QueryCitation, QueryRequest, QueryResponse
from app.security.detect import contains_known_pii, detect_spans
from app.security.detokenize import detokenize_response, hash_query
from app.security.tokenize import tokenize_record
from app.services.embeddings import embed_text
from app.services.reasoning import answer_query_with_citations, unknown_tokens
from app.services.retrieval import retrieve_hits

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
def query(payload: QueryRequest, db: Session = Depends(get_db)) -> QueryResponse:
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

    query_embedding, embedding_mode = embed_text(sanitized_question)
    hits = retrieve_hits(db, query_embedding, k=5)
    cited_answer, reasoning_mode = answer_query_with_citations(sanitized_question, hits)
    raw_answer = cited_answer.answer
    known_tokens = set(db.scalars(select(TokenVaultEntry.token)).all())
    invented = unknown_tokens(raw_answer, known_tokens)
    if invented:
        raise HTTPException(status_code=502, detail="The model returned an unknown protected token")
    final_answer = detokenize_response(
        db, raw_answer, payload.role.value, hash_query(payload.question)
    )
    mode = reasoning_mode if embedding_mode != "offline-demo" else "offline-demo"
    return QueryResponse(
        answer=final_answer,
        model_answer=raw_answer,
        model_question=sanitized_question,
        sources_used=len(hits),
        mode=mode,
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
