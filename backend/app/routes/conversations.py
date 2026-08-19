from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.db import get_db
from app.models import ConversationTurnCitation, TokenizedContent
from app.schemas import (
    ConversationCreateResponse,
    ConversationDeleteResponse,
    ConversationResponse,
    ConversationTurnResponse,
    UserRole,
)
from app.services.conversations import (
    create_conversation,
    delete_conversation,
    get_active_conversation,
    load_recent_turns,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _http_error(error: ValueError) -> HTTPException:
    code = str(error)
    return HTTPException(
        status_code=410 if code == "conversation_expired" else 404,
        detail=code,
    )


@router.post("", response_model=ConversationCreateResponse)
def create(principal: CurrentUser, db: Session = Depends(get_db)) -> ConversationCreateResponse:
    conversation = create_conversation(db, str(principal.tenant_id), str(principal.user_id))
    return ConversationCreateResponse(
        conversation_id=conversation.id,
        status=conversation.status,
        expires_at=conversation.expires_at,
    )


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get(
    conversation_id: str,
    principal: CurrentUser,
    db: Session = Depends(get_db),
) -> ConversationResponse:
    try:
        conversation = get_active_conversation(
            db, conversation_id, str(principal.tenant_id), str(principal.user_id)
        )
    except ValueError as error:
        raise _http_error(error) from error
    turns = load_recent_turns(db, conversation.id, str(principal.tenant_id))
    responses: list[ConversationTurnResponse] = []
    for turn in turns:
        source_ids = list(
            db.scalars(
                select(TokenizedContent.source_record_id)
                .join(
                    ConversationTurnCitation,
                    ConversationTurnCitation.tokenized_content_id == TokenizedContent.id,
                )
                .where(ConversationTurnCitation.turn_id == turn.id)
                .order_by(ConversationTurnCitation.ordinal)
            ).all()
        )
        responses.append(
            ConversationTurnResponse(
                turn_id=turn.id,
                sequence_number=turn.sequence_number,
                user_role=UserRole(turn.user_role),
                protected_question=turn.protected_question,
                protected_answer=turn.protected_answer,
                protected_brief=turn.protected_brief,
                query_intent=turn.query_intent,
                source_systems=turn.source_systems,
                reasoning_mode=turn.reasoning_mode,
                insufficient_evidence=turn.insufficient_evidence,
                citation_source_record_ids=source_ids,
                created_at=turn.created_at,
            )
        )
    return ConversationResponse(
        conversation_id=conversation.id,
        status=conversation.status,
        expires_at=conversation.expires_at,
        turns=responses,
    )


@router.delete("/{conversation_id}", response_model=ConversationDeleteResponse)
def remove(
    conversation_id: str,
    principal: CurrentUser,
    db: Session = Depends(get_db),
) -> ConversationDeleteResponse:
    try:
        delete_conversation(db, conversation_id, str(principal.tenant_id), str(principal.user_id))
    except ValueError as error:
        raise _http_error(error) from error
    return ConversationDeleteResponse(conversation_id=conversation_id, status="deleted")
