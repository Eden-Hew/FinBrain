from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, ProcessRecommendation, TokenizedContent, WorkflowAuditEntry
from app.schemas import ProcessAnalysisRequest, UserRole
from app.services.recommendations import analyze_processes, decide_recommendation
from app.services.workflow_audit import verify_workflow_chain


def _ready_record(index: int, source: str) -> TokenizedContent:
    return TokenizedContent(
        source_record_id=f"{source}:{index}",
        source_system=source,
        record_type="customer_message" if source == "telegram" else "email",
        content_text=f"Protected overdue approval evidence {index}.",
        summary=f"Approval delay {index} requires attention.",
        embedding=[1.0, 0.0],
        structured_summary={
            "summary": f"Approval delay {index} requires attention.",
            "category": "approval_delay",
            "action_required": True,
            "priority": "high",
        },
        processing_status="ready",
        occurred_at=datetime.now(UTC),
    )


def test_analysis_persists_cross_source_evidence_and_audit(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setenv("MORPHEUS_API_KEY", "")
    with Session(engine) as db:
        db.add_all(
            [_ready_record(1, "telegram"), _ready_record(2, "email"), _ready_record(3, "email")]
        )
        db.commit()

        result = analyze_processes(
            db,
            ProcessAnalysisRequest(
                source_systems=["telegram", "email"],
                minimum_evidence=3,
            ),
            role=UserRole.OWNER_DIRECTOR,
        )

        assert result.status == "proposed"
        assert result.record_count == 3
        assert set(result.source_systems) == {"telegram", "email"}
        assert len(result.evidence) == 3
        assert verify_workflow_chain(db)


def test_recommendation_transition_is_persistent_and_protected(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setenv("MORPHEUS_API_KEY", "")
    monkeypatch.setenv("ENABLE_GLINER", "false")
    with Session(engine) as db:
        db.add_all([_ready_record(i, "email") for i in range(1, 4)])
        db.commit()
        proposed = analyze_processes(
            db,
            ProcessAnalysisRequest(
                source_systems=["email"],
                minimum_evidence=3,
            ),
            role=UserRole.OWNER_DIRECTOR,
        )
        approved = decide_recommendation(
            db,
            proposed.id,
            decision="approved",
            role=UserRole.OWNER_DIRECTOR,
            comment="Call 012-345 6789 before rollout.",
        )

        assert approved.status == "approved"
        assert db.get(ProcessRecommendation, proposed.id).status == "approved"
        assert len(db.scalars(select(WorkflowAuditEntry)).all()) == 2
        assert verify_workflow_chain(db)
