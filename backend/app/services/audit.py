import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import AuditLogEntry, utcnow


def _event_payload(
    role: str,
    token: str,
    authorized: bool,
    query_hash: str,
    ts: datetime,
    actor_ref: str = "legacy",
) -> dict:
    canonical_ts = ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)
    payload = {
        "authorized": authorized,
        "query_hash": query_hash,
        "token": token,
        "ts": canonical_ts.isoformat(timespec="microseconds"),
        "user_role": role,
    }
    if actor_ref != "legacy":
        payload["actor_ref"] = actor_ref
    return payload


def _compute_hash(previous_hash: str, event: dict) -> str:
    canonical = json.dumps(event, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{canonical}{previous_hash}".encode()).hexdigest()


def write_audit_entry(
    db: Session,
    role: str,
    token: str,
    authorized: bool,
    query_hash: str,
    *,
    tenant_id: str,
    actor_ref: str = "legacy",
) -> None:
    lock_key = f"finbrain:audit-log:{tenant_id}"
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("select pg_advisory_xact_lock(hashtext(:key))"), {"key": lock_key})
        previous_hash = db.scalar(
            text("select public.finbrain_audit_tail('disclosure', cast(:tenant_id as uuid))"),
            {"tenant_id": tenant_id},
        )
    else:
        last = db.scalar(
            select(AuditLogEntry)
            .where(AuditLogEntry.tenant_id == tenant_id)
            .order_by(AuditLogEntry.id.desc())
            .limit(1)
        )
        previous_hash = last.event_hash if last else "genesis"
    timestamp = utcnow()
    event = _event_payload(role, token, authorized, query_hash, timestamp, actor_ref)
    db.add(
        AuditLogEntry(
            tenant_id=tenant_id,
            prev_hash=previous_hash,
            event_hash=_compute_hash(previous_hash, event),
            user_role=role,
            token=token,
            authorized=authorized,
            query_hash=query_hash,
            actor_ref=actor_ref,
            ts=timestamp,
        )
    )
    # The session disables autoflush. Flush explicitly so another disclosure
    # in the same response sees this event as the current end of the chain.
    db.flush()


def verify_audit_chain(db: Session, tenant_id: str | None = None) -> bool:
    previous_hash = "genesis"
    rows = db.scalars(
        select(AuditLogEntry).where(AuditLogEntry.tenant_id == tenant_id).order_by(AuditLogEntry.id)
    ).all()
    for entry in rows:
        event = _event_payload(
            entry.user_role,
            entry.token,
            entry.authorized,
            entry.query_hash,
            entry.ts,
            entry.actor_ref,
        )
        if entry.prev_hash != previous_hash or entry.event_hash != _compute_hash(
            previous_hash, event
        ):
            return False
        previous_hash = entry.event_hash
    return True
