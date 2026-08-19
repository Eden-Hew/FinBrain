from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ProtectedTokenRegistry, TokenizedContent, TokenVaultEntry
from app.schemas import PrivacyEraseResponse, PrivacyTokenResponse, UserRole
from app.security.keyring import decrypt_vault_entry
from app.services.audit import write_audit_entry
from app.services.workflow_audit import write_workflow_event


def _referencing_source_record_ids(db: Session, tenant_id: str, token: str) -> list[str]:
    rows = db.scalars(
        select(TokenizedContent.source_record_id).where(
            TokenizedContent.tenant_id == tenant_id,
            TokenizedContent.content_text.contains(token),
        )
    ).all()
    return sorted(set(rows))


def export_token(
    db: Session,
    token: str,
    tenant_id: str,
    *,
    role: UserRole,
    query_hash: str,
    actor_ref: str,
) -> PrivacyTokenResponse:
    """PDPA "right to access", scoped to one specific protected value.

    Full "everything about person X" access needs identity resolution across
    tokens, which Phase 6 does not yet cover outside e-invoice buyers (see
    INDUSTRIAL_ROADMAP_PLAN.md) -- this is the narrower, already-buildable slice:
    what is stored under one known token, and every record that currently
    contains it. Revealing the decrypted value goes through the same
    allowed_roles gate and disclosure-audit trail as normal query-time
    detokenization, since it is the same kind of disclosure.
    """
    registry = db.get(ProtectedTokenRegistry, token)
    if registry is None or registry.tenant_id != tenant_id:
        raise LookupError("protected_token_not_found")
    entry = db.scalar(
        select(TokenVaultEntry).where(
            TokenVaultEntry.token == token, TokenVaultEntry.tenant_id == tenant_id
        )
    )
    authorized = entry is not None and role.value in entry.allowed_roles
    decrypted_value = decrypt_vault_entry(db, entry) if authorized and entry is not None else None
    write_audit_entry(
        db,
        role.value,
        token,
        authorized,
        query_hash,
        tenant_id=tenant_id,
        actor_ref=actor_ref,
    )
    db.commit()
    return PrivacyTokenResponse(
        token=token,
        entity_type=registry.entity_type,
        masked_value=registry.masked_value,
        decrypted_value=decrypted_value,
        source_record_ids=_referencing_source_record_ids(db, tenant_id, token),
    )


def erase_token(
    db: Session,
    token: str,
    tenant_id: str,
    *,
    role: UserRole,
    actor_ref: str,
) -> PrivacyEraseResponse:
    """PDPA erasure for one specific protected value (crypto-shredding).

    Deletes only the token_vault ciphertext row, not the protected_token_registry
    metadata (entity_type + masked_value, never the secret itself). That is enough:
    detokenize_response_with_trace already treats a missing vault entry as
    unauthorized and falls back to the masked value, so every past and future
    reference to this token in already-protected text degrades gracefully to
    "restricted" instead of ever being decryptable again -- with no changes
    needed to the query/detokenization path itself.
    """
    entry = db.scalar(
        select(TokenVaultEntry).where(
            TokenVaultEntry.token == token, TokenVaultEntry.tenant_id == tenant_id
        )
    )
    if entry is None:
        raise LookupError("protected_token_not_found_or_already_erased")
    entity_type = entry.entity_type
    db.delete(entry)
    write_workflow_event(
        db,
        event_type="privacy_token_erased",
        actor_role=role.value,
        actor_ref=actor_ref,
        resource_type="token_vault",
        resource_id=token,
        tenant_id=tenant_id,
        event_payload={"entity_type": entity_type},
    )
    db.commit()
    return PrivacyEraseResponse(token=token, erased=True)
