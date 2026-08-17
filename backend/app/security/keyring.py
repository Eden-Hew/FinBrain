import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import TokenVaultEntry, VaultKeyVersion, utcnow
from app.security.crypto import decrypt_value, derive_key_from_secret, encrypt_value

ACTIVE = "active"
DECRYPT_ONLY = "decrypt_only"
RETIRED = "retired"


def _master_key() -> bytes:
    return derive_key_from_secret(
        get_settings().vault_wrapping_secret.encode(),
        info=b"finbrain:vault-master-wrap:v1",
    )


def _wrap_aad(version: int) -> bytes:
    return f"finbrain:vault-generation:{version}".encode()


def _entry_aad(*, token: str, entity_type: str, source_record_id: str, version: int) -> bytes:
    return "\x1f".join(
        ["finbrain-vault-v1", token, entity_type, source_record_id, str(version)]
    ).encode()


def ensure_active_key(db: Session) -> VaultKeyVersion:
    active = db.scalar(select(VaultKeyVersion).where(VaultKeyVersion.status == ACTIVE))
    if active is not None:
        return active
    return create_key_version(db, activate=True)


def create_key_version(db: Session, *, activate: bool = False) -> VaultKeyVersion:
    latest = db.scalar(select(VaultKeyVersion).order_by(VaultKeyVersion.version.desc()).limit(1))
    version = 1 if latest is None else latest.version + 1
    generation_key = os.urandom(32)
    wrapped, nonce = encrypt_value(
        generation_key.hex(),
        _master_key(),
        _wrap_aad(version),
    )
    active = VaultKeyVersion(
        version=version,
        wrapped_key=wrapped,
        wrap_nonce=nonce,
        status=ACTIVE if activate else "pending",
        activated_at=utcnow() if activate else None,
    )
    db.add(active)
    db.flush()
    return active


def unwrap_generation_key(row: VaultKeyVersion) -> bytes:
    if row.status == RETIRED:
        raise ValueError("vault_key_retired")
    value = decrypt_value(
        row.wrapped_key,
        row.wrap_nonce,
        _master_key(),
        _wrap_aad(row.version),
    )
    return bytes.fromhex(value)


def generation_key(db: Session, version: int) -> bytes:
    row = db.get(VaultKeyVersion, version)
    if row is None:
        raise ValueError("vault_key_version_missing")
    return unwrap_generation_key(row)


def token_key(generation: bytes, *, token: str, version: int) -> bytes:
    return derive_key_from_secret(
        generation,
        info=f"finbrain:vault-token:{version}:{token}".encode(),
    )


def encrypt_vault_value(
    db: Session,
    *,
    token: str,
    entity_type: str,
    source_record_id: str,
    value: str,
) -> tuple[bytes, bytes, int]:
    active = ensure_active_key(db)
    ciphertext, nonce = encrypt_vault_value_with_version(
        db,
        version=active.version,
        token=token,
        entity_type=entity_type,
        source_record_id=source_record_id,
        value=value,
    )
    return ciphertext, nonce, active.version


def encrypt_vault_value_with_version(
    db: Session,
    *,
    version: int,
    token: str,
    entity_type: str,
    source_record_id: str,
    value: str,
) -> tuple[bytes, bytes]:
    key = token_key(
        generation_key(db, version),
        token=token,
        version=version,
    )
    ciphertext, nonce = encrypt_value(
        value,
        key,
        _entry_aad(
            token=token,
            entity_type=entity_type,
            source_record_id=source_record_id,
            version=version,
        ),
    )
    return ciphertext, nonce


def decrypt_vault_entry(db: Session, entry: TokenVaultEntry) -> str:
    key = token_key(
        generation_key(db, entry.key_version),
        token=entry.token,
        version=entry.key_version,
    )
    return decrypt_value(
        entry.encrypted_value,
        entry.nonce,
        key,
        _entry_aad(
            token=entry.token,
            entity_type=entry.entity_type,
            source_record_id=entry.source_record_id,
            version=entry.key_version,
        ),
    )
