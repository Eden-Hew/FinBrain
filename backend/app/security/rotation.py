from datetime import timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import TokenVaultEntry, VaultKeyVersion, VaultRotationJob, utcnow
from app.security.keyring import (
    ACTIVE,
    DECRYPT_ONLY,
    RETIRED,
    create_key_version,
    decrypt_vault_entry,
    encrypt_vault_value_with_version,
    ensure_active_key,
)
from app.services.workflow_audit import write_workflow_event


def _rotation_lock(db: Session) -> None:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("select pg_advisory_xact_lock(hashtext('finbrain:vault-rotation'))"))


def start_rotation(db: Session) -> VaultRotationJob:
    _rotation_lock(db)
    running = db.scalar(
        select(VaultRotationJob).where(VaultRotationJob.status.in_(["pending", "running"]))
    )
    if running is not None:
        return running
    current = ensure_active_key(db)
    target = create_key_version(db)
    total = db.scalar(
        select(func.count()).select_from(TokenVaultEntry).where(
            TokenVaultEntry.key_version == current.version
        )
    ) or 0
    current.status = DECRYPT_ONLY
    target.status = ACTIVE
    target.activated_at = utcnow()
    job = VaultRotationJob(
        from_version=current.version,
        to_version=target.version,
        status="running",
        rows_total=total,
    )
    db.add(job)
    db.flush()
    write_workflow_event(
        db,
        event_type="vault_rotation_started",
        actor_role="system_worker",
        actor_ref="vault-rotation-worker",
        resource_type="vault_key_version",
        resource_id=str(target.version),
        event_payload={
            "from_version": current.version,
            "to_version": target.version,
            "rows_total": total,
        },
    )
    db.commit()
    return job


def rotate_batch(db: Session, job: VaultRotationJob) -> VaultRotationJob:
    if job.status not in {"pending", "running"}:
        return job
    settings = get_settings()
    statement = (
        select(TokenVaultEntry)
        .where(TokenVaultEntry.key_version == job.from_version)
        .order_by(TokenVaultEntry.token)
        .limit(settings.vault_rotation_batch_size)
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True)
    rows = list(db.scalars(statement).all())
    for entry in rows:
        plaintext = decrypt_vault_entry(db, entry)
        ciphertext, nonce = encrypt_vault_value_with_version(
            db,
            version=job.to_version,
            token=entry.token,
            entity_type=entry.entity_type,
            source_record_id=entry.source_record_id,
            value=plaintext,
        )
        entry.encrypted_value = ciphertext
        entry.nonce = nonce
        entry.key_version = job.to_version
        job.rows_rotated += 1
        job.last_token = entry.token
    if not rows:
        previous = db.get(VaultKeyVersion, job.from_version)
        if previous is not None:
            previous.status = RETIRED
            previous.retired_at = utcnow()
        job.status = "completed"
        job.completed_at = utcnow()
        write_workflow_event(
            db,
            event_type="vault_rotation_completed",
            actor_role="system_worker",
            actor_ref="vault-rotation-worker",
            resource_type="vault_key_version",
            resource_id=str(job.to_version),
            event_payload={
                "from_version": job.from_version,
                "to_version": job.to_version,
                "rows_rotated": job.rows_rotated,
            },
        )
    db.commit()
    return job


def run_rotation(db: Session) -> VaultRotationJob:
    job = start_rotation(db)
    while job.status in {"pending", "running"}:
        job = rotate_batch(db, job)
    return job


def rotation_due(db: Session) -> bool:
    active = ensure_active_key(db)
    reference = active.activated_at or active.created_at
    return utcnow() >= reference + timedelta(days=get_settings().vault_rotation_interval_days)


def rotate_if_due(db: Session) -> VaultRotationJob | None:
    if not get_settings().vault_auto_rotation_enabled:
        db.commit()
        return None
    unfinished = db.scalar(
        select(VaultRotationJob).where(VaultRotationJob.status.in_(["pending", "running"]))
    )
    if unfinished is not None:
        while unfinished.status in {"pending", "running"}:
            unfinished = rotate_batch(db, unfinished)
        return unfinished
    if not rotation_due(db):
        db.commit()
        return None
    return run_rotation(db)
