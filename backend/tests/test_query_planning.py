from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, TokenizedContent
from app.routes import query as query_route
from app.schemas import CitedAnswer, QueryRequest, UserRole
from app.security import detect
from app.services.query_planning import QueryIntent, plan_query


def _record(index: int, source: str, *, embedding: list[float] | None = None):
    return TokenizedContent(
        source_record_id=f"{source}:{index}",
        source_system=source,
        record_type="customer_email" if source == "email" else "operations_minutes",
        content_text=f"Protected {source} record {index} about an approval delay.",
        summary=f"{source} approval summary {index}.",
        structured_summary={
            "summary": f"{source} approval summary {index}.",
            "category": "payment_approval_delay",
            "action_required": True,
            "priority": "high",
        },
        embedding=embedding or [1.0, 0.0],
        processing_status="ready",
    )


def test_planner_recognizes_exact_email_listing_before_tokenization():
    available = ["email", "telegram", "meeting_notes"]

    first = plan_query("show all email sources", available)
    second = plan_query("show me all content where source_system is email", available)

    assert first.intent is QueryIntent.LIST_RECORDS
    assert first.source_systems == ("email",)
    assert second.intent is QueryIntent.LIST_RECORDS
    assert second.source_systems == ("email",)


def test_planner_recognizes_source_count_questions():
    available = ["email", "telegram", "meeting_notes"]

    for question in (
        "what is the total number of email sources?",
        "how many email records are there?",
        "count all email messages",
    ):
        plan = plan_query(question, available)
        assert plan.intent is QueryIntent.COUNT_RECORDS
        assert plan.source_systems == ("email",)

    source_count = plan_query("how many source systems are available?", available)
    assert source_count.intent is QueryIntent.COUNT_SOURCES
    assert source_count.source_systems == ()


def test_generic_csv_means_uploaded_spreadsheet_while_bank_csv_stays_explicit():
    available = ["bank_csv", "spreadsheet", "email"]

    generic_listing = plan_query("show all csv", available)
    generic_count = plan_query("count number of csv rows", available)
    bank_listing = plan_query("show all bank csv records", available)

    assert generic_listing.intent is QueryIntent.LIST_RECORDS
    assert generic_listing.source_systems == ("spreadsheet",)
    assert generic_count.intent is QueryIntent.COUNT_RECORDS
    assert generic_count.source_systems == ("spreadsheet",)
    assert generic_count.filters.record_types == ("invoice_row",)
    assert bank_listing.intent is QueryIntent.LIST_RECORDS
    assert bank_listing.source_systems == ("bank_csv",)


def test_planner_treats_each_source_analysis_as_exhaustive():
    plan = plan_query(
        "summarize each email source formatted nicely",
        ["email", "telegram", "meeting_notes"],
    )

    assert plan.intent is QueryIntent.ANALYZE_ALL
    assert plan.source_systems == ("email",)


def test_email_count_uses_structured_inventory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([_record(index, "email") for index in range(1, 7)])
        db.commit()

        response = query_route.query(
            QueryRequest(
                question="what is the total number of email sources?",
                role=UserRole.GENERAL_EMPLOYEE,
            ),
            db,
        )

    assert response.mode == "structured-filter"
    assert response.answer == "email: 6 ready record(s)."
    assert response.sources_used == 0
    assert response.citations == []


def test_analyze_all_email_records_uses_every_sql_match(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    captured: dict[str, int] = {}

    def fake_answer(_question, hits):
        captured["hit_count"] = len(hits)
        return (
            CitedAnswer(
                answer="All six protected email records were analyzed.",
                citations=[f"SOURCE-{index}" for index in range(1, len(hits) + 1)],
            ),
            "test",
        )

    monkeypatch.setattr(query_route, "answer_all_query_with_citations", fake_answer)
    with Session(engine) as db:
        db.add_all([_record(index, "email") for index in range(1, 7)])
        db.commit()

        response = query_route.query(
            QueryRequest(
                question="summarize each email source formatted nicely",
                role=UserRole.GENERAL_EMPLOYEE,
            ),
            db,
        )

    assert captured["hit_count"] == 6
    assert response.sources_used == 6
    assert len(response.citations) == 6


def test_ordinary_analytical_question_uses_every_sql_eligible_record(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        query_route,
        "answer_all_query_with_citations",
        lambda _question, hits: (
            CitedAnswer(
                answer="Ranked protected evidence.",
                citations=[f"SOURCE-{index}" for index in range(1, len(hits) + 1)],
            ),
            "test",
        ),
    )
    with Session(engine) as db:
        db.add_all([_record(index, "email") for index in range(1, 7)])
        db.commit()

        response = query_route.query(
            QueryRequest(
                question="What email issue is most relevant?",
                role=UserRole.GENERAL_EMPLOYEE,
            ),
            db,
        )

    assert response.sources_used == 6
    assert len(response.citations) == 6


def test_unfiltered_analytical_question_uses_all_ready_sources(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        query_route,
        "answer_all_query_with_citations",
        lambda _question, hits: (
            CitedAnswer(
                answer="Complete cross-source protected evidence.",
                citations=[f"SOURCE-{index}" for index in range(1, len(hits) + 1)],
            ),
            "test",
        ),
    )
    with Session(engine) as db:
        db.add_all(
            [_record(index, "email") for index in range(1, 7)]
            + [_record(index, "telegram") for index in range(1, 3)]
        )
        db.commit()

        response = query_route.query(
            QueryRequest(
                question="What business issues need attention?",
                role=UserRole.GENERAL_EMPLOYEE,
            ),
            db,
        )

    assert response.sources_used == 8
    assert len(response.citations) == 8
    assert {citation.source_system for citation in response.citations} == {
        "email",
        "telegram",
    }


def test_exact_email_listing_bypasses_reasoning():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(
            [
                _record(1, "email"),
                _record(2, "email"),
                _record(3, "email"),
                _record(4, "meeting_notes"),
            ]
        )
        db.commit()

        response = query_route.query(
            QueryRequest(
                question="show me all content where source_system is email",
                role=UserRole.GENERAL_EMPLOYEE,
            ),
            db,
        )

    assert response.mode == "structured-filter"
    assert response.sources_used == 3
    assert len(response.citations) == 3
    assert {citation.source_system for citation in response.citations} == {"email"}
    assert "Found 3 ready record(s) from email" in response.answer


def test_semantic_question_is_scoped_to_mentioned_source(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        query_route,
        "answer_all_query_with_citations",
        lambda _question, hits: (
            CitedAnswer(
                answer="Protected email evidence.",
                citations=[f"SOURCE-{index}" for index in range(1, len(hits) + 1)],
            ),
            "test",
        ),
    )
    with Session(engine) as db:
        db.add_all([_record(1, "email"), _record(2, "telegram")])
        db.commit()

        response = query_route.query(
            QueryRequest(
                question="What payment issues came from email?",
                role=UserRole.GENERAL_EMPLOYEE,
            ),
            db,
        )

    assert response.sources_used == 1
    assert {citation.source_system for citation in response.citations} == {"email"}


class _FakeDetector:
    def __init__(self, entities):
        self.entities = entities

    def predict_entities(self, *_args, **_kwargs):
        return self.entities


def test_gliner_rejects_bare_email_and_structural_or_organizational_roles(monkeypatch):
    text = "email customer unassigned named approver Ahmad Faizal lim@example.com"
    entities = [
        {"start": 0, "end": 5, "text": "email", "label": "email"},
        {"start": 6, "end": 14, "text": "customer", "label": "person"},
        {"start": 15, "end": 25, "text": "unassigned", "label": "person"},
        {"start": 26, "end": 40, "text": "named approver", "label": "person"},
        {"start": 41, "end": 53, "text": "Ahmad Faizal", "label": "person"},
        {"start": 54, "end": 69, "text": "lim@example.com", "label": "email"},
    ]
    monkeypatch.setattr(
        detect,
        "get_settings",
        lambda: SimpleNamespace(enable_gliner=True),
    )
    monkeypatch.setattr(detect, "_get_model", lambda: _FakeDetector(entities))

    spans = detect._gliner_detect(text)

    assert [(span.text, span.label) for span in spans] == [
        ("Ahmad Faizal", "person"),
        ("lim@example.com", "email"),
    ]
