import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import WorkflowAuditEntry, utcnow


def _payload(
    *,
    event_type: str,
    actor_role: str,
    actor_ref: str,
    resource_type: str,
    resource_id: str,
    event_payload: dict,
    created_at: datetime,
) -> dict:
    timestamp = (
        created_at.replace(tzinfo=UTC)
        if created_at.tzinfo is None
        else created_at.astimezone(UTC)
    )
    return {
        "actor_ref": actor_ref,
        "actor_role": actor_role,
        "created_at": timestamp.isoformat(timespec="microseconds"),
        "event_payload": event_payload,
        "event_type": event_type,
        "resource_id": resource_id,
        "resource_type": resource_type,
    }


def _hash(previous_hash: str, payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{canonical}{previous_hash}".encode()).hexdigest()


def write_workflow_event(
    db: Session,
    *,
    event_type: str,
    actor_role: str,
    actor_ref: str,
    resource_type: str,
    resource_id: str,
    event_payload: dict,
) -> WorkflowAuditEntry:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("select pg_advisory_xact_lock(hashtext('finbrain:workflow-audit'))"))
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        previous_hash = db.scalar(text("select public.finbrain_audit_tail('workflow')"))
    else:
        last = db.scalar(select(WorkflowAuditEntry).order_by(WorkflowAuditEntry.id.desc()).limit(1))
        previous_hash = last.event_hash if last else "genesis"
    timestamp = utcnow()
    payload = _payload(
        event_type=event_type,
        actor_role=actor_role,
        actor_ref=actor_ref,
        resource_type=resource_type,
        resource_id=resource_id,
        event_payload=event_payload,
        created_at=timestamp,
    )
    row = WorkflowAuditEntry(
        prev_hash=previous_hash,
        event_hash=_hash(previous_hash, payload),
        event_type=event_type,
        actor_role=actor_role,
        actor_ref=actor_ref,
        resource_type=resource_type,
        resource_id=resource_id,
        event_payload=event_payload,
        created_at=timestamp,
    )
    db.add(row)
    db.flush()
    return row


def verify_workflow_chain(db: Session) -> bool:
    previous_hash = "genesis"
    for row in db.scalars(select(WorkflowAuditEntry).order_by(WorkflowAuditEntry.id)).all():
        payload = _payload(
            event_type=row.event_type,
            actor_role=row.actor_role,
            actor_ref=row.actor_ref,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            event_payload=row.event_payload,
            created_at=row.created_at,
        )
        if row.prev_hash != previous_hash or row.event_hash != _hash(previous_hash, payload):
            return False
        previous_hash = row.event_hash
    return True
