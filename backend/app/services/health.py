from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IntegrationStatus, utcnow

BACKEND_STARTED_AT: datetime = utcnow()


@dataclass(frozen=True, slots=True)
class ServiceStatus:
    key: str
    label: str
    configured: bool
    status: str
    mode: str
    started_at: datetime | None
    last_heartbeat_at: datetime | None
    detector_ready: bool
    failure_code: str | None


def write_heartbeat(
    db: Session,
    *,
    key: str,
    status: str,
    mode: str,
    started_at: datetime | None,
    detector_ready: bool = False,
    failure_code: str | None = None,
) -> None:
    """Upsert a worker heartbeat without overwriting a prior process start time."""
    row = db.get(IntegrationStatus, key) or IntegrationStatus(
        integration_key=key,
        status=status,
        mode=mode,
        detector_ready=detector_ready,
        started_at=started_at,
        last_heartbeat_at=utcnow(),
        failure_code=failure_code,
    )
    row.status = status
    row.mode = mode
    row.detector_ready = detector_ready
    row.last_heartbeat_at = utcnow()
    row.failure_code = failure_code
    if row.started_at is None:
        row.started_at = started_at
    db.add(row)
    db.commit()


def _tz(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def heartbeat_rows(db: Session) -> dict[str, IntegrationStatus]:
    return {row.integration_key: row for row in db.scalars(select(IntegrationStatus)).all()}


def uptime_seconds(started_at: datetime | None) -> float | None:
    if started_at is None:
        return None
    started = _tz(started_at)
    if started is None:
        return None
    return max(0.0, (utcnow() - started).total_seconds())
