import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    Conversation,
    ConversationTurn,
    ConversationTurnCitation,
    TokenizedContent,
)
from app.services.retrieval import RetrievalHit

CONVERSATION_TTL = timedelta(hours=24)
HISTORY_TURN_LIMIT = 6
REFERENCE_PATTERN = re.compile(
    r"\b(?:those|these|them|it|that|that record|the (?:first|second|third|previous) "
    r"(?:one|result)|(?:first|second|third) one)\b",
    re.IGNORECASE,
)
ORDINALS = {"first": 1, "second": 2, "third": 3}


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def create_conversation(db: Session) -> Conversation:
    now = _now()
    conversation = Conversation(
        id=str(uuid.uuid4()),
        status="active",
        expires_at=now + CONVERSATION_TTL,
    )
    db.add(conversation)
    db.commit()
    return conversation


def get_active_conversation(db: Session, conversation_id: str) -> Conversation:
    try:
        normalized_id = str(uuid.UUID(conversation_id))
    except (ValueError, AttributeError) as error:
        raise ValueError("invalid_conversation_id") from error
    conversation = db.get(Conversation, normalized_id)
    if conversation is None or conversation.status == "deleted":
        raise ValueError("conversation_not_found")
    if conversation.status == "expired" or _aware(conversation.expires_at) <= _now():
        conversation.status = "expired"
        db.commit()
        raise ValueError("conversation_expired")
    return conversation


def get_or_create_conversation(
    db: Session, conversation_id: str | None
) -> Conversation:
    return (
        get_active_conversation(db, conversation_id)
        if conversation_id
        else create_conversation(db)
    )


def load_recent_turns(db: Session, conversation_id: str) -> list[ConversationTurn]:
    rows = db.scalars(
        select(ConversationTurn)
        .where(ConversationTurn.conversation_id == conversation_id)
        .order_by(ConversationTurn.sequence_number.desc())
        .limit(HISTORY_TURN_LIMIT)
    ).all()
    return list(reversed(rows))


def protected_history(db: Session, conversation_id: str) -> str:
    turns = load_recent_turns(db, conversation_id)
    if not turns:
        return ""
    blocks = [
        f"[TURN-{turn.sequence_number} USER] {turn.protected_question}\n"
        f"[TURN-{turn.sequence_number} ASSISTANT] {turn.protected_answer}"
        for turn in turns
    ]
    return "Protected conversation history:\n" + "\n\n".join(blocks)


def is_referential_question(question: str) -> bool:
    return bool(REFERENCE_PATTERN.search(question))


def _requested_ordinal(question: str) -> int | None:
    lowered = question.casefold()
    for word, ordinal in ORDINALS.items():
        if re.search(rf"\b(?:the\s+)?{word}\s+(?:one|result)\b", lowered):
            return ordinal
    return None


def prior_citation_hits(
    db: Session,
    conversation_id: str,
    question: str,
    *,
    source_systems: tuple[str, ...] = (),
) -> list[RetrievalHit]:
    prior_turns = db.scalars(
        select(ConversationTurn)
        .where(ConversationTurn.conversation_id == conversation_id)
        .order_by(ConversationTurn.sequence_number.desc())
        .limit(HISTORY_TURN_LIMIT)
    ).all()
    ordinal = _requested_ordinal(question)
    citations = []
    for prior_turn in prior_turns:
        candidates = db.execute(
            select(ConversationTurnCitation, TokenizedContent)
            .join(
                TokenizedContent,
                TokenizedContent.id == ConversationTurnCitation.tokenized_content_id,
            )
            .where(ConversationTurnCitation.turn_id == prior_turn.id)
            .order_by(ConversationTurnCitation.ordinal)
        ).all()
        if ordinal is not None:
            candidates = [pair for pair in candidates if pair[0].ordinal == ordinal]
        if candidates:
            citations = candidates
            break
    if source_systems:
        citations = [pair for pair in citations if pair[1].source_system in source_systems]
    return [
        RetrievalHit(
            content_id=row.id,
            source_record_id=row.source_record_id,
            source_system=row.source_system,
            record_type=row.record_type,
            occurred_at=row.occurred_at,
            protected_excerpt=row.content_text,
            protected_summary=row.summary,
            similarity=1.0,
        )
        for _citation, row in citations
        if row.processing_status == "ready"
    ]


def persist_turn(
    db: Session,
    conversation: Conversation,
    *,
    user_role: str,
    protected_question: str,
    protected_answer: str,
    query_intent: str,
    source_systems: list[str],
    reasoning_mode: str,
    insufficient_evidence: bool,
    cited_hits: list[RetrievalHit],
) -> ConversationTurn:
    sequence = (
        db.scalar(
            select(func.max(ConversationTurn.sequence_number)).where(
                ConversationTurn.conversation_id == conversation.id
            )
        )
        or 0
    ) + 1
    turn = ConversationTurn(
        conversation_id=conversation.id,
        sequence_number=sequence,
        user_role=user_role,
        protected_question=protected_question,
        protected_answer=protected_answer,
        query_intent=query_intent,
        source_systems=source_systems,
        reasoning_mode=reasoning_mode,
        insufficient_evidence=insufficient_evidence,
    )
    db.add(turn)
    db.flush()
    for ordinal, hit in enumerate(cited_hits, 1):
        db.add(
            ConversationTurnCitation(
                turn_id=turn.id,
                ordinal=ordinal,
                tokenized_content_id=hit.content_id,
            )
        )
    now = _now()
    conversation.updated_at = now
    conversation.expires_at = now + CONVERSATION_TTL
    db.commit()
    return turn


def delete_conversation(db: Session, conversation_id: str) -> None:
    conversation = get_active_conversation(db, conversation_id)
    turn_ids = select(ConversationTurn.id).where(
        ConversationTurn.conversation_id == conversation.id
    )
    db.execute(
        delete(ConversationTurnCitation).where(
            ConversationTurnCitation.turn_id.in_(turn_ids)
        )
    )
    db.execute(
        delete(ConversationTurn).where(
            ConversationTurn.conversation_id == conversation.id
        )
    )
    conversation.status = "deleted"
    db.commit()


def expire_stale_conversations(db: Session) -> int:
    rows = db.scalars(
        select(Conversation).where(
            Conversation.status == "active", Conversation.expires_at <= _now()
        )
    ).all()
    for row in rows:
        row.status = "expired"
    db.commit()
    return len(rows)
