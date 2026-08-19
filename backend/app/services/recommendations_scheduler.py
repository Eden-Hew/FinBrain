import logging
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, set_worker_context
from app.models import Tenant
from app.schemas import ProcessAnalysisRequest, UserRole
from app.services.health import write_heartbeat
from app.services.query_planning import source_inventory
from app.services.recommendations import analyze_processes

ACTOR_REF = "recommendations-scheduler"
logger = logging.getLogger(__name__)


def _tenant_ids(db: Session) -> list[str]:
    return [str(row) for row in db.scalars(select(Tenant.id)).all()]


def _request_for_tenant(db: Session, tenant_id: str) -> ProcessAnalysisRequest | None:
    """Scan every source system the tenant actually has ready records in.

    Unlike the manual "Analyze Processes" button (which asks a human to pick 1-2
    sources up front), the scheduler has no one to ask, so it covers whatever the
    tenant has rather than a fixed default pair. Returns None when the tenant has
    no ready content at all, so callers can skip it without a wasted call.
    """
    sources = [source for source, count in source_inventory(db, tenant_id) if count > 0]
    if not sources:
        return None
    return ProcessAnalysisRequest(source_systems=sources[:10])


def run_once() -> int:
    """Run one analysis pass across every tenant. Returns the tenant count processed."""
    with SessionLocal() as db:
        set_worker_context(db, actor_ref=ACTOR_REF)
        tenant_ids = _tenant_ids(db)

    processed = 0
    for tenant_id in tenant_ids:
        with SessionLocal() as db:
            set_worker_context(db, actor_ref=ACTOR_REF, tenant_id=tenant_id)
            request = _request_for_tenant(db, tenant_id)
            if request is None:
                continue
            processed += 1
            try:
                analyze_processes(
                    db,
                    request,
                    role=UserRole.OWNER_DIRECTOR,
                    tenant_id=tenant_id,
                    actor_ref=ACTOR_REF,
                )
            except ValueError:
                # No recurring pattern met the minimum-evidence bar this pass -- expected
                # and common, not a failure.
                db.rollback()
            except Exception:
                logger.exception(
                    "recommendations_scheduler_tenant_failed", extra={"tenant_id": tenant_id}
                )
                db.rollback()
    return processed


def main() -> None:
    settings = get_settings()
    if not settings.recommendations_auto_analysis_enabled:
        print("Recommendations scheduler disabled.")
        return
    print("Recommendations scheduler started.")
    started_at = datetime.now(UTC)
    first_heartbeat = True
    while True:
        try:
            with SessionLocal() as db:
                set_worker_context(db, actor_ref=ACTOR_REF)
                write_heartbeat(
                    db,
                    key="recommendations-scheduler",
                    instance_id=settings.effective_service_instance_id,
                    status="healthy",
                    mode="scheduled",
                    started_at=started_at,
                    reset_started_at=first_heartbeat,
                )
                first_heartbeat = False
        except Exception:
            print("recommendations_scheduler_heartbeat_failed")
        try:
            processed = run_once()
            print(f"Recommendations scheduler pass complete: {processed} tenant(s) analyzed.")
        except Exception:
            logger.exception("recommendations_scheduler_run_failed")
        time.sleep(settings.recommendations_analysis_interval_seconds)


if __name__ == "__main__":
    main()
