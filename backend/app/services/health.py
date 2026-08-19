from dataclasses import dataclass
from datetime import UTC, datetime

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


def heartbeat_key(instance_id: str, service_key: str) -> str:
    """Return the database key for one service in one runtime instance."""
    return f"{instance_id}:{service_key}"


def write_heartbeat(
    db: Session,
    *,
    key: str,
    instance_id: str,
    status: str,
    mode: str,
    started_at: datetime | None,
    detector_ready: bool = False,
    failure_code: str | None = None,
    reset_started_at: bool = False,
) -> None:
    """Upsert one instance-scoped worker heartbeat."""
    scoped_key = heartbeat_key(instance_id, key)
    row = db.get(IntegrationStatus, scoped_key) or IntegrationStatus(
        integration_key=scoped_key,
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
    if reset_started_at or row.started_at is None:
        row.started_at = started_at
    db.add(row)
    db.commit()


def _tz(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def heartbeat_rows(db: Session, instance_id: str) -> dict[str, IntegrationStatus]:
    service_keys = ("telegram", "email", "vault-rotation", "recommendations-scheduler")
    return {
        service_key: row
        for service_key in service_keys
        if (row := db.get(IntegrationStatus, heartbeat_key(instance_id, service_key))) is not None
    }


def uptime_seconds(started_at: datetime | None) -> float | None:
    if started_at is None:
        return None
    started = _tz(started_at)
    if started is None:
        return None
    return max(0.0, (utcnow() - started).total_seconds())
