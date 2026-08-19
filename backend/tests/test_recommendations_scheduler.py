from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import Base, ProcessRecommendation, Tenant, TokenizedContent
from app.services import recommendations_scheduler as scheduler

TENANT_A = "00000000-0000-0000-0000-0000000000a1"
TENANT_B = "00000000-0000-0000-0000-0000000000b2"


def _ready_record(index: int, source: str, tenant_id: str) -> TokenizedContent:
    return TokenizedContent(
        tenant_id=tenant_id,
        source_record_id=f"{tenant_id}:{source}:{index}",
        source_system=source,
        record_type="customer_message" if source == "telegram" else "email",
        content_text=f"Protected overdue approval evidence {index}.",
        summary=f"Approval delay {index} requires attention.",
        structured_summary={
            "summary": f"Approval delay {index} requires attention.",
            "category": "approval_delay",
            "action_required": True,
            "priority": "high",
        },
        processing_status="ready",
        occurred_at=datetime.now(UTC),
    )


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def test_run_once_generates_recommendations_only_for_qualifying_tenants(monkeypatch):
    monkeypatch.setenv("MORPHEUS_API_KEY", "")
    db = _session()
    try:
        db.add_all(
            [
                Tenant(id=TENANT_A, name="Tenant A", slug="tenant-a"),
                Tenant(id=TENANT_B, name="Tenant B", slug="tenant-b"),
                # Tenant A has enough recurring evidence to clear the default bar.
                _ready_record(1, "telegram", TENANT_A),
                _ready_record(2, "email", TENANT_A),
                _ready_record(3, "email", TENANT_A),
                # Tenant B has ready content but not enough of it to form a pattern.
                _ready_record(1, "telegram", TENANT_B),
            ]
        )
        db.commit()

        monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
        # Session.close() would tear down the shared in-memory db between the
        # per-tenant `with SessionLocal() as db:` blocks in run_once().
        monkeypatch.setattr(db, "close", lambda: None)

        processed = scheduler.run_once()

        assert processed == 2
        recs_a = db.scalars(
            select(ProcessRecommendation).where(ProcessRecommendation.tenant_id == TENANT_A)
        ).all()
        recs_b = db.scalars(
            select(ProcessRecommendation).where(ProcessRecommendation.tenant_id == TENANT_B)
        ).all()
        assert len(recs_a) == 1
        assert recs_a[0].record_count == 3
        assert recs_b == []
    finally:
        db.close()


def test_run_once_skips_tenants_with_no_ready_content(monkeypatch):
    db = _session()
    try:
        db.add(Tenant(id=TENANT_A, name="Tenant A", slug="tenant-a"))
        db.commit()

        monkeypatch.setattr(scheduler, "SessionLocal", lambda: db)
        monkeypatch.setattr(db, "close", lambda: None)

        processed = scheduler.run_once()

        assert processed == 0
    finally:
        db.close()
