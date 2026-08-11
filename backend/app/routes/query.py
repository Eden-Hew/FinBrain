import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import TokenVaultEntry
from app.schemas import QueryRequest, QueryResponse
from app.security.detect import contains_known_pii, detect_spans
from app.security.detokenize import detokenize_response, hash_query
from app.security.tokenize import tokenize_record
from app.services.embeddings import embed_text
from app.services.reasoning import answer_query, unknown_tokens
from app.services.retrieval import retrieve_top_k

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
    chunks = retrieve_top_k(db, query_embedding, k=5)
    raw_answer, reasoning_mode = answer_query(sanitized_question, chunks)
    known_tokens = set(db.scalars(select(TokenVaultEntry.token)).all())
    invented = unknown_tokens(raw_answer, known_tokens)
    if invented:
        raise HTTPException(status_code=502, detail="The model returned an unknown protected token")
    final_answer = detokenize_response(
        db, raw_answer, payload.role.value, hash_query(payload.question)
    )
    mode = "gemini" if embedding_mode == reasoning_mode == "gemini" else "offline-demo"
    return QueryResponse(
        answer=final_answer,
        model_answer=raw_answer,
        model_question=sanitized_question,
        sources_used=len(chunks),
        mode=mode,
    )
