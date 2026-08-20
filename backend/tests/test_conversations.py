from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import (
    DEFAULT_TENANT_ID,
    Base,
    Conversation,
    ConversationTurn,
    ConversationTurnCitation,
    TokenizedContent,
)
from app.routes.query import query
from app.schemas import CitedAnswer, QueryRequest
from app.services.conversation_planning import ConversationalPlan
from app.services.conversations import (
    create_conversation,
    delete_conversation,
    expire_stale_conversations,
    get_active_conversation,
    is_referential_question,
    load_recent_turns,
    persist_turn,
    prior_citation_hits,
    protected_history,
    protected_planning_history,
)
from app.services.retrieval import RetrievalHit
from tests.auth_support import principal


def _database() -> tuple:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def _ready_record(db: Session, source_id: str, source: str) -> TokenizedContent:
    row = TokenizedContent(
        source_record_id=source_id,
        source_system=source,
        record_type="message",
        content_text=f"Protected {source} content.",
        processing_status="ready",
    )
    db.add(row)
    db.commit()
    return row


def _hit(row: TokenizedContent) -> RetrievalHit:
    return RetrievalHit(
        content_id=row.id,
        source_record_id=row.source_record_id,
        source_system=row.source_system,
        record_type=row.record_type,
        occurred_at=row.occurred_at,
        protected_excerpt=row.content_text,
        protected_summary=row.summary,
        similarity=1.0,
    )


def test_conversation_stores_only_protected_turn_and_citation_references():
    engine, db = _database()
    row = _ready_record(db, "email:opaque-1", "email")
    try:
        conversation = create_conversation(db, DEFAULT_TENANT_ID)
        turn = persist_turn(
            db,
            conversation,
            user_role="general_employee",
            protected_question="What did PERSON_0011223344 request?",
            protected_answer="PERSON_0011223344 requested review [SOURCE-1].",
            query_intent="semantic",
            source_systems=["email"],
            reasoning_mode="test",
            insufficient_evidence=False,
            cited_hits=[_hit(row)],
        )

        stored = db.get(ConversationTurn, turn.id)
        citation = db.scalar(select(ConversationTurnCitation))
        assert stored.protected_question == "What did PERSON_0011223344 request?"
        assert stored.protected_answer.startswith("PERSON_0011223344")
        assert citation.tokenized_content_id == row.id
        assert "Ahmad" not in repr(stored.__dict__)
    finally:
        db.close()
        engine.dispose()


def test_recent_history_is_bounded_to_six_turns():
    engine, db = _database()
    try:
        conversation = create_conversation(db, DEFAULT_TENANT_ID)
        for index in range(1, 8):
            persist_turn(
                db,
                conversation,
                user_role="general_employee",
                protected_question=f"Protected question {index}",
                protected_answer=f"Protected answer {index}",
                query_intent="semantic",
                source_systems=[],
                reasoning_mode="test",
                insufficient_evidence=False,
                cited_hits=[],
            )
        turns = load_recent_turns(db, conversation.id, DEFAULT_TENANT_ID)
        history = protected_history(db, conversation.id, DEFAULT_TENANT_ID)
        assert [turn.sequence_number for turn in turns] == [2, 3, 4, 5, 6, 7]
        assert "TURN-1" not in history
        assert "TURN-7" in history
    finally:
        db.close()
        engine.dispose()


def test_referential_follow_up_reuses_prior_citations_with_filters_and_ordinals():
    engine, db = _database()
    email = _ready_record(db, "email:1", "email")
    telegram = _ready_record(db, "telegram:1", "telegram")
    try:
        conversation = create_conversation(db, DEFAULT_TENANT_ID)
        persist_turn(
            db,
            conversation,
            user_role="general_employee",
            protected_question="Summarize all records",
            protected_answer="Two records [SOURCE-1] [SOURCE-2].",
            query_intent="analyze_all",
            source_systems=[],
            reasoning_mode="test",
            insufficient_evidence=False,
            cited_hits=[_hit(email), _hit(telegram)],
        )

        assert is_referential_question("Which of those came from email?")
        assert is_referential_question("Yes, describe that")
        assert is_referential_question("Show his contact")
        assert is_referential_question("How do I contact him?")
        assert is_referential_question("What did that customer request?")
        assert is_referential_question("Suggest response")
        assert is_referential_question("Draft a reply")
        email_hits = prior_citation_hits(
            db,
            conversation.id,
            "Which of those came from email?",
            DEFAULT_TENANT_ID,
            source_systems=("email",),
        )
        second = prior_citation_hits(
            db, conversation.id, "Tell me about the second one", DEFAULT_TENANT_ID
        )
        assert [hit.source_record_id for hit in email_hits] == ["email:1"]
        assert [hit.source_record_id for hit in second] == ["telegram:1"]
        for question in (
            "Tell me about email 2",
            "Tell me about the 2nd email",
            "About 2",
            "Describe the second email",
            "Inspect SOURCE-2",
        ):
            assert is_referential_question(question)
            selected = prior_citation_hits(db, conversation.id, question, DEFAULT_TENANT_ID)
            assert [hit.source_record_id for hit in selected] == ["telegram:1"]
    finally:
        db.close()
        engine.dispose()


def test_ordinal_falls_back_to_nearest_turn_that_contains_requested_position():
    engine, db = _database()
    first = _ready_record(db, "email:1", "email")
    second = _ready_record(db, "email:2", "email")
    third = _ready_record(db, "email:3", "email")
    try:
        conversation = create_conversation(db, DEFAULT_TENANT_ID)
        persist_turn(
            db,
            conversation,
            user_role="general_employee",
            protected_question="Describe each email",
            protected_answer="Three protected emails.",
            query_intent="semantic",
            source_systems=["email"],
            reasoning_mode="test",
            insufficient_evidence=False,
            cited_hits=[_hit(first), _hit(second), _hit(third)],
        )
        persist_turn(
            db,
            conversation,
            user_role="general_employee",
            protected_question="Tell me about a named customer",
            protected_answer="One protected customer.",
            query_intent="semantic",
            source_systems=["email"],
            reasoning_mode="test",
            insufficient_evidence=False,
            cited_hits=[_hit(second)],
        )

        hits = prior_citation_hits(
            db, conversation.id, "Tell me about the third one", DEFAULT_TENANT_ID
        )

        assert [hit.source_record_id for hit in hits] == ["email:3"]
    finally:
        db.close()
        engine.dispose()


def test_expiry_and_delete_remove_replayable_turns():
    engine, db = _database()
    try:
        expired = create_conversation(db, DEFAULT_TENANT_ID)
        expired.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        assert expire_stale_conversations(db) == 1
        try:
            get_active_conversation(db, expired.id, DEFAULT_TENANT_ID)
        except ValueError as error:
            assert str(error) == "conversation_expired"
        else:
            raise AssertionError("Expired conversation remained active")

        active = create_conversation(db, DEFAULT_TENANT_ID)
        persist_turn(
            db,
            active,
            user_role="general_employee",
            protected_question="Protected question",
            protected_answer="Protected answer",
            query_intent="semantic",
            source_systems=[],
            reasoning_mode="test",
            insufficient_evidence=True,
            cited_hits=[],
        )
        delete_conversation(db, active.id, DEFAULT_TENANT_ID)
        assert db.get(Conversation, active.id).status == "deleted"
        assert (
            db.scalar(select(ConversationTurn).where(ConversationTurn.conversation_id == active.id))
            is None
        )
    finally:
        db.close()
        engine.dispose()


def test_query_route_creates_context_and_intersects_follow_up_sources(monkeypatch):
    engine, db = _database()
    _ready_record(db, "email:context", "email")
    _ready_record(db, "telegram:context", "telegram")
    try:
        first = query(
            QueryRequest(
                question="Summarize all records",
            ),
            principal(),
            db,
        )
        captured: dict[str, str] = {}

        def answer_follow_up(question, hits):
            captured["question"] = question
            return (
                CitedAnswer(
                    answer="The selected protected email is relevant [SOURCE-1].",
                    citations=["SOURCE-1"],
                    insufficient_evidence=False,
                ),
                "test",
            )

        monkeypatch.setattr(
            "app.routes.query.answer_all_query_with_citations",
            answer_follow_up,
        )
        second = query(
            QueryRequest(
                question="Which of those came from email?",
                conversation_id=first.conversation_id,
            ),
            principal(),
            db,
        )

        assert first.conversation_id is not None
        assert first.turn_id is not None
        assert second.conversation_id == first.conversation_id
        assert second.turn_id != first.turn_id
        assert [citation.source_system for citation in second.citations] == ["email"]
        turns = load_recent_turns(db, first.conversation_id, DEFAULT_TENANT_ID)
        assert len(turns) == 2
        assert turns[1].protected_question == "Which of those came from email?"
        assert "Protected conversation history" not in turns[1].protected_question
        assert "deterministic conversation resolver has already selected" in captured["question"]
        assert captured["question"].endswith("User follow-up: Which of those came from email?")
    finally:
        db.close()
        engine.dispose()


def test_count_turn_preserves_hidden_record_context_for_follow_up():
    engine, db = _database()
    _ready_record(db, "email:count-1", "email")
    _ready_record(db, "email:count-2", "email")
    try:
        first = query(
            QueryRequest(
                question="How many email records are ready?",
            ),
            principal(),
            db,
        )
        second = query(
            QueryRequest(
                question="Tell me what each of them means",
                conversation_id=first.conversation_id,
            ),
            principal(),
            db,
        )

        assert first.sources_used == 0
        assert first.citations == []
        assert first.answer == "email: 2 ready record(s)."
        assert second.sources_used == 2
        assert len(second.citations) == 2
    finally:
        db.close()
        engine.dispose()


def test_planning_history_contains_only_protected_turns_and_citation_metadata():
    engine, db = _database()
    row = _ready_record(db, "email:planning", "email")
    try:
        conversation = create_conversation(db, DEFAULT_TENANT_ID)
        persist_turn(
            db,
            conversation,
            user_role="general_employee",
            protected_question="What did PERSON_aabbccddee request?",
            protected_answer="PERSON_aabbccddee requested help.",
            query_intent="lookup",
            source_systems=["email"],
            reasoning_mode="test",
            insufficient_evidence=False,
            cited_hits=[_hit(row)],
        )

        history = protected_planning_history(db, conversation.id, DEFAULT_TENANT_ID)

        assert history == [
            {
                "turn": 1,
                "user": "What did PERSON_aabbccddee request?",
                "assistant": "PERSON_aabbccddee requested help.",
                "intent": "lookup",
                "citations": [
                    {"ordinal": 1, "source_system": "email", "record_type": "message"}
                ],
            }
        ]
        assert "Protected email content" not in repr(history)
    finally:
        db.close()
        engine.dispose()


def test_person_pronoun_follow_up_reuses_single_cited_customer_as_compact_lookup(monkeypatch):
    engine, db = _database()
    customer = _ready_record(db, "email:sheng", "email")
    try:
        conversation = create_conversation(
            db,
            DEFAULT_TENANT_ID,
            str(principal().user_id),
        )
        persist_turn(
            db,
            conversation,
            user_role="general_employee",
            protected_question="Find PERSON_aabbccddee",
            protected_answer="The customer is available.",
            query_intent="lookup",
            source_systems=[],
            reasoning_mode="test",
            insufficient_evidence=False,
            cited_hits=[_hit(customer)],
        )
        captured: dict[str, object] = {}

        def answer_follow_up(question, hits, *, response_style="analysis"):
            captured["question"] = question
            captured["hits"] = hits
            captured["style"] = response_style
            return CitedAnswer(answer="The contact is available.", citations=["SOURCE-1"]), "test"

        monkeypatch.setattr(
            "app.routes.query.answer_all_query_with_citations",
            answer_follow_up,
        )
        response = query(
            QueryRequest(
                question="How do I contact him?",
                conversation_id=conversation.id,
            ),
            principal(),
            db,
        )

        assert response.query_intent == "lookup"
        assert response.intelligence_brief is None
        assert response.protected_intelligence_brief is None
        assert response.citations[0].source_record_id == "email:sheng"
        assert captured["style"] == "compact"
        assert len(captured["hits"]) == 1
        assert "deterministic conversation resolver" in str(captured["question"])
    finally:
        db.close()
        engine.dispose()


def test_ambiguous_person_pronoun_requests_a_name_without_calling_model(monkeypatch):
    engine, db = _database()
    first = _ready_record(db, "email:first-person", "email")
    second = _ready_record(db, "email:second-person", "email")
    try:
        conversation = create_conversation(
            db,
            DEFAULT_TENANT_ID,
            str(principal().user_id),
        )
        persist_turn(
            db,
            conversation,
            user_role="general_employee",
            protected_question="List customer contacts",
            protected_answer="Two customers are available.",
            query_intent="lookup",
            source_systems=[],
            reasoning_mode="test",
            insufficient_evidence=False,
            cited_hits=[_hit(first), _hit(second)],
        )
        monkeypatch.setattr(
            "app.routes.query.answer_all_query_with_citations",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("ambiguous reference must not reach the model")
            ),
        )

        response = query(
            QueryRequest(question="Show his contact", conversation_id=conversation.id),
            principal(),
            db,
        )

        assert response.mode == "conversation-clarification"
        assert response.citations == []
        assert "which person" in response.answer.casefold()
    finally:
        db.close()
        engine.dispose()


def test_elliptical_suggest_response_reuses_immediately_previous_citation(monkeypatch):
    engine, db = _database()
    wong = _ready_record(db, "telegram:wong-mei-ling", "telegram")
    try:
        conversation = create_conversation(
            db,
            DEFAULT_TENANT_ID,
            str(principal().user_id),
        )
        persist_turn(
            db,
            conversation,
            user_role="general_employee",
            protected_question="What issue does PERSON_aabbccddee have?",
            protected_answer="The shipment contained damaged units.",
            query_intent="lookup",
            source_systems=[],
            reasoning_mode="test",
            insufficient_evidence=False,
            cited_hits=[_hit(wong)],
        )
        captured: dict[str, object] = {}

        def answer_follow_up(question, hits, *, response_style="analysis"):
            captured["question"] = question
            captured["source_ids"] = [hit.source_record_id for hit in hits]
            captured["style"] = response_style
            return (
                CitedAnswer(
                    answer="Acknowledge the damaged items and confirm replacement timing.",
                    citations=["SOURCE-1"],
                ),
                "test",
            )

        monkeypatch.setattr(
            "app.routes.query.answer_all_query_with_citations",
            answer_follow_up,
        )
        response = query(
            QueryRequest(question="suggest response", conversation_id=conversation.id),
            principal(),
            db,
        )

        assert captured["source_ids"] == ["telegram:wong-mei-ling"]
        assert captured["style"] == "compact"
        assert "deterministic conversation resolver" in str(captured["question"])
        assert response.query_intent == "lookup"
        assert response.citations[0].source_record_id == "telegram:wong-mei-ling"
        assert response.intelligence_brief is None
    finally:
        db.close()
        engine.dispose()


def test_model_planner_can_follow_topic_to_an_older_cited_turn(monkeypatch):
    engine, db = _database()
    older_topic = _ready_record(db, "telegram:older-topic", "telegram")
    newer_topic = _ready_record(db, "email:newer-topic", "email")
    try:
        conversation = create_conversation(
            db,
            DEFAULT_TENANT_ID,
            str(principal().user_id),
        )
        persist_turn(
            db,
            conversation,
            user_role="general_employee",
            protected_question="Discuss PERSON_aabbccddee",
            protected_answer="The protected shipment was damaged.",
            query_intent="lookup",
            source_systems=["telegram"],
            reasoning_mode="test",
            insufficient_evidence=False,
            cited_hits=[_hit(older_topic)],
        )
        persist_turn(
            db,
            conversation,
            user_role="general_employee",
            protected_question="Discuss PERSON_ffeeddccbb",
            protected_answer="The protected refund is pending.",
            query_intent="lookup",
            source_systems=["email"],
            reasoning_mode="test",
            insufficient_evidence=False,
            cited_hits=[_hit(newer_topic)],
        )
        monkeypatch.setattr(
            "app.routes.query.plan_conversation",
            lambda **_kwargs: ConversationalPlan(
                intent="lookup",
                referenced_turn=1,
                response_style="compact",
                needs_clarification=False,
            ),
        )
        captured = {}

        def answer_follow_up(_question, hits, *, response_style="analysis"):
            captured["ids"] = [hit.source_record_id for hit in hits]
            captured["style"] = response_style
            return CitedAnswer(answer="Draft the protected reply.", citations=["SOURCE-1"]), "test"

        monkeypatch.setattr(
            "app.routes.query.answer_all_query_with_citations",
            answer_follow_up,
        )

        response = query(
            QueryRequest(
                question="Suggest a response to the damaged shipment",
                conversation_id=conversation.id,
            ),
            principal(),
            db,
        )

        assert captured["ids"] == ["telegram:older-topic"]
        assert captured["style"] == "compact"
        assert response.citations[0].source_record_id == "telegram:older-topic"
        assert response.exposure_receipt.external_ai_used is True
    finally:
        db.close()
        engine.dispose()
