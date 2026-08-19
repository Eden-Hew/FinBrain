from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.models import Base, TokenizedContent
from app.services.query_filters import (
    QueryFilters,
    count_eligible_records,
    eligible_statement,
    list_eligible_hits,
)
from app.services.query_planning import QueryIntent, plan_query

NOW = datetime(2026, 8, 14, 4, 0, tzinfo=UTC)


def _record(
    source_id: str,
    *,
    source: str = "email",
    record_type: str = "customer_email",
    occurred_at: datetime = NOW,
    category: str = "payment_approval_delay",
    priority: str = "high",
    action_required: bool = True,
    metadata: dict | None = None,
) -> TokenizedContent:
    return TokenizedContent(
        source_record_id=source_id,
        source_system=source,
        record_type=record_type,
        occurred_at=occurred_at,
        content_text=f"Protected content for {source_id}.",
        summary="Protected summary.",
        structured_summary={
            "summary": "Protected summary.",
            "category": category,
            "priority": priority,
            "action_required": action_required,
        },
        safe_metadata=metadata or {},
        processing_status="ready",
    )


def test_planner_builds_typed_filters_for_acceptance_questions():
    available = ["email", "telegram", "spreadsheet", "support_ticket"]
    cases = [
        (
            "How many high-priority payment approval delays came from email this week?",
            QueryIntent.COUNT_RECORDS,
            {
                "source_systems": ("email",),
                "categories": ("payment_approval_delay",),
                "priorities": ("high",),
            },
        ),
        (
            "List overdue spreadsheet invoices without an owner.",
            QueryIntent.LIST_RECORDS,
            {
                "source_systems": ("spreadsheet",),
                "record_types": ("invoice_row", "einvoice"),
                "metadata_equals": (
                    ("overdue", "overdue"),
                    ("has_assigned_owner", "false"),
                ),
            },
        ),
        (
            "Summarize support tickets from the last 7 days.",
            QueryIntent.SEMANTIC,
            {
                "source_systems": ("support_ticket",),
                "record_types": ("support_ticket",),
            },
        ),
        (
            "Which of those Telegram records still needs action?",
            QueryIntent.SEMANTIC,
            {"source_systems": ("telegram",), "action_required": True},
        ),
    ]

    for question, intent, expected in cases:
        plan = plan_query(
            question,
            available,
            now=NOW,
            timezone_name="Asia/Kuala_Lumpur",
        )
        assert plan.intent is intent
        for field, value in expected.items():
            if field == "metadata_equals":
                assert ("status", value[0][1]) in plan.filters.metadata_equals
                assert value[1] in plan.filters.metadata_equals
            else:
                assert getattr(plan.filters, field) == value


def test_planner_converts_kuala_lumpur_calendar_ranges_to_utc():
    today = plan_query("records today", [], now=NOW).filters
    yesterday = plan_query("records yesterday", [], now=NOW).filters
    this_week = plan_query("records this week", [], now=NOW).filters
    last_week = plan_query("records last week", [], now=NOW).filters
    this_month = plan_query("records this month", [], now=NOW).filters

    assert today.occurred_from == datetime(2026, 8, 13, 16, tzinfo=UTC)
    assert today.occurred_to == datetime(2026, 8, 14, 16, tzinfo=UTC)
    assert yesterday.occurred_from == datetime(2026, 8, 12, 16, tzinfo=UTC)
    assert this_week.occurred_from == datetime(2026, 8, 9, 16, tzinfo=UTC)
    assert last_week.occurred_from == datetime(2026, 8, 2, 16, tzinfo=UTC)
    assert last_week.occurred_to == datetime(2026, 8, 9, 16, tzinfo=UTC)
    assert this_month.occurred_from == datetime(2026, 7, 31, 16, tzinfo=UTC)
    assert this_month.occurred_to == datetime(2026, 8, 31, 16, tzinfo=UTC)


def test_count_list_and_analysis_selection_share_the_same_eligible_ids():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(
            [
                _record("match"),
                _record("wrong-priority", priority="low"),
                _record("wrong-source", source="telegram"),
                _record("too-old", occurred_at=NOW - timedelta(days=14)),
            ]
        )
        db.commit()
        filters = plan_query(
            "How many high-priority payment approval delays came from email this week?",
            ["email", "telegram"],
            now=NOW,
        ).filters
        hits = list_eligible_hits(db, filters)

        assert count_eligible_records(db, filters) == 1
        assert [hit.source_record_id for hit in hits] == ["match"]
        assert [hit.content_id for hit in list_eligible_hits(db, filters)] == [
            hit.content_id for hit in hits
        ]


def test_portable_json_filters_work_on_sqlite_and_compile_for_postgres():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    filters = QueryFilters(
        source_systems=("spreadsheet",),
        record_types=("invoice_row",),
        metadata_equals=(("status", "overdue"), ("has_assigned_owner", "false")),
    )
    with Session(engine) as db:
        db.add_all(
            [
                _record(
                    "spreadsheet:match",
                    source="spreadsheet",
                    record_type="invoice_row",
                    metadata={"status": "overdue", "has_assigned_owner": "false"},
                ),
                _record(
                    "spreadsheet:owned",
                    source="spreadsheet",
                    record_type="invoice_row",
                    metadata={"status": "overdue", "has_assigned_owner": "true"},
                ),
            ]
        )
        db.commit()
        assert [hit.source_record_id for hit in list_eligible_hits(db, filters)] == [
            "spreadsheet:match"
        ]

    compiled = str(eligible_statement(filters).compile(dialect=postgresql.dialect()))
    assert "tokenized_content.safe_metadata" in compiled
    assert "tokenized_content.source_system" in compiled


def test_query_builder_rejects_non_allowlisted_metadata_keys():
    try:
        eligible_statement(QueryFilters(metadata_equals=(("customer", "unsafe"),)))
    except ValueError as error:
        assert str(error) == "unsupported_metadata_filter"
    else:
        raise AssertionError("Question-derived metadata key entered a SQL expression")
