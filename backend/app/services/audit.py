import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLogEntry, utcnow


def _event_payload(role: str, token: str, authorized: bool, query_hash: str, ts: datetime) -> dict:
    canonical_ts = ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)
    return {
        "authorized": authorized,
        "query_hash": query_hash,
        "token": token,
        "ts": canonical_ts.isoformat(timespec="microseconds"),
        "user_role": role,
    }


def _compute_hash(previous_hash: str, event: dict) -> str:
    canonical = json.dumps(event, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{canonical}{previous_hash}".encode()).hexdigest()


def write_audit_entry(
    db: Session, role: str, token: str, authorized: bool, query_hash: str
) -> None:
    last = db.scalar(select(AuditLogEntry).order_by(AuditLogEntry.id.desc()).limit(1))
    previous_hash = last.event_hash if last else "genesis"
    timestamp = utcnow()
    event = _event_payload(role, token, authorized, query_hash, timestamp)
    db.add(
        AuditLogEntry(
            prev_hash=previous_hash,
            event_hash=_compute_hash(previous_hash, event),
            user_role=role,
            token=token,
            authorized=authorized,
            query_hash=query_hash,
            ts=timestamp,
        )
    )
    # The session disables autoflush. Flush explicitly so another disclosure
    # in the same response sees this event as the current end of the chain.
    db.flush()


def verify_audit_chain(db: Session) -> bool:
    previous_hash = "genesis"
    for entry in db.scalars(select(AuditLogEntry).order_by(AuditLogEntry.id)).all():
        event = _event_payload(
            entry.user_role, entry.token, entry.authorized, entry.query_hash, entry.ts
        )
        if entry.prev_hash != previous_hash or entry.event_hash != _compute_hash(
            previous_hash, event
        ):
            return False
        previous_hash = entry.event_hash
    return True
