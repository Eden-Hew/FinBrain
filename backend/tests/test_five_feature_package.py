from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import (
    Base,
    Conversation,
    ConversationTurn,
    ConversationTurnCitation,
    TokenizedContent,
    WorkflowAuditEntry,
)
from app.routes.query_artifacts import citation_detail, compare_roles
from app.schemas import RoleComparisonRequest, UserRole
from app.security.detect import detect_spans
from app.security.tokenize import tokenize_record
from app.services.intelligence import build_protected_brief, validate_protected_brief
from app.services.recommendations import create_recommendation_from_turn
from app.services.retrieval import RetrievalHit
from tests.auth_support import principal


def _database() -> tuple:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def _turn_with_amount(db: Session) -> tuple[ConversationTurn, TokenizedContent, str]:
    raw = "Meranti Trading has an overdue payment approval for RM 4,500 with no owner."
    protected, entries = tokenize_record(raw, detect_spans(raw), "five-feature-test")
    db.add_all(entries)
    content = TokenizedContent(
        source_record_id="email:five-feature-test",
        source_system="email",
        record_type="email",
        content_text=protected,
        summary=protected,
        processing_status="ready",
        safe_metadata={},
    )
    conversation = Conversation(
        id="10000000-0000-0000-0000-000000000001",
        created_by_user_id=str(principal().user_id),
        status="active",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add_all([content, conversation])
    db.flush()
    turn = ConversationTurn(
        conversation_id=conversation.id,
        sequence_number=1,
        user_role="finance_ops",
        protected_question="Why is the approval delayed?",
        protected_answer=protected,
        protected_brief={
            "subject_label": "Payment approval intelligence",
            "status": "at_risk",
            "executive_summary": protected,
            "claims": [
                {
                    "id": "claim-1",
                    "statement": protected,
                    "citation_ids": ["SOURCE-1"],
                    "relation": "supporting",
                }
            ],
            "timeline": [],
            "open_commitments": [],
            "risks": [],
            "missing_information": [],
            "recommended_action": {
                "id": "recommended-action",
                "title": "Assign an approval owner",
                "rationale": "Assign a named owner to the cited approval.",
                "suggested_owner": "Finance Operations",
                "priority": "high",
                "citation_ids": ["SOURCE-1"],
            },
        },
        query_intent="semantic",
        source_systems=["email"],
        reasoning_mode="offline-demo",
        insufficient_evidence=False,
    )
    db.add(turn)
    db.flush()
    db.add(
        ConversationTurnCitation(
            turn_id=turn.id,
            ordinal=1,
            tokenized_content_id=content.id,
        )
    )
    db.commit()
    return turn, content, protected


def test_intelligence_brief_is_grounded_in_current_citations():
    hit = RetrievalHit(
        content_id=1,
        source_record_id="email:1",
        source_system="email",
        record_type="email",
        occurred_at=datetime.now(UTC),
        protected_excerpt="An overdue approval has no assigned owner.",
        protected_summary="An overdue approval has no assigned owner.",
        similarity=1.0,
    )
    brief = build_protected_brief(
        question="Why are approvals delayed?",
        protected_answer="The approval is delayed and needs action.",
        hits=[hit],
        cited_ids={"SOURCE-1"},
        insufficient_evidence=False,
    )
    assert brief is not None
    assert brief.status == "at_risk"
    assert brief.claims[0].citation_ids == ["SOURCE-1"]
    assert brief.missing_information
    assert brief.recommended_action is not None

    invalid = brief.model_copy(deep=True)
    invalid.claims[0].citation_ids = ["SOURCE-99"]
    with pytest.raises(ValueError, match="unknown citation"):
        validate_protected_brief(
            invalid,
            allowed_citations={"SOURCE-1"},
            protected_context=hit.protected_excerpt,
        )

    invented_token = brief.model_copy(deep=True)
    invented_token.claims[0].statement = "Unknown PERSON_aaaaaaaaaa"
    with pytest.raises(ValueError, match="unknown protected token"):
        validate_protected_brief(
            invented_token,
            allowed_citations={"SOURCE-1"},
            protected_context=hit.protected_excerpt,
        )

    residual_pii = brief.model_copy(deep=True)
    residual_pii.claims[0].statement = "Contact customer@example.com"
    with pytest.raises(ValueError, match="recognizable sensitive data"):
        validate_protected_brief(
            residual_pii,
            allowed_citations={"SOURCE-1"},
            protected_context=hit.protected_excerpt,
        )


def test_evidence_and_role_comparison_reuse_protected_turn():
    engine, db = _database()
    try:
        turn, _content, protected = _turn_with_amount(db)
        employee_principal = principal(UserRole.GENERAL_EMPLOYEE)
        employee = citation_detail(
            turn.id,
            "SOURCE-1",
            employee_principal,
            db,
        )
        assert "RM2.5K–5K" in employee.authorized_excerpt
        assert employee.withheld_tokens >= 1

        comparison = compare_roles(
            turn.id,
            RoleComparisonRequest(
                comparison_roles=[UserRole.GENERAL_EMPLOYEE, UserRole.FINANCE_OPS],
            ),
            replace(employee_principal, role=UserRole.COMPLIANCE),
            db,
        )
        assert comparison.protected_answer == protected
        assert len(comparison.results) == 2
        assert "RM2.5K–5K" in comparison.results[0].answer
        assert "RM 4,500" in comparison.results[1].answer

        with pytest.raises(HTTPException) as error:
            compare_roles(
                turn.id,
                RoleComparisonRequest(
                    comparison_roles=[UserRole.OWNER_DIRECTOR],
                ),
                replace(employee_principal, role=UserRole.FINANCE_OPS),
                db,
            )
        assert error.value.status_code == 403
    finally:
        db.close()
        engine.dispose()


def test_query_turn_can_create_idempotent_evidence_backed_recommendation():
    engine, db = _database()
    try:
        turn, _content, _protected = _turn_with_amount(db)
        unrelated = TokenizedContent(
            source_record_id="email:unrelated",
            source_system="email",
            record_type="email",
            content_text="An unrelated protected record.",
            summary="An unrelated protected record.",
            processing_status="ready",
            safe_metadata={},
        )
        db.add(unrelated)
        db.flush()
        db.add(
            ConversationTurnCitation(
                turn_id=turn.id,
                ordinal=2,
                tokenized_content_id=unrelated.id,
            )
        )
        db.commit()
        first = create_recommendation_from_turn(
            db,
            turn.id,
            role=UserRole.FINANCE_OPS,
            action_id="recommended-action",
        )
        second = create_recommendation_from_turn(
            db,
            turn.id,
            role=UserRole.FINANCE_OPS,
            action_id="recommended-action",
        )
        assert first.id == second.id
        assert first.record_count == 1
        assert first.origin_type == "query_brief"
        assert first.origin_turn_id == turn.id
        assert first.origin_query_hash
        assert first.evidence[0].source_system == "email"
        assert db.query(WorkflowAuditEntry).count() == 1

        with pytest.raises(PermissionError):
            create_recommendation_from_turn(
                db,
                turn.id,
                role=UserRole.GENERAL_EMPLOYEE,
                action_id="recommended-action",
            )
    finally:
        db.close()
        engine.dispose()
