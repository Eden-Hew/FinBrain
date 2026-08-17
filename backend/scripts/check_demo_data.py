import re
from collections import Counter

from sqlalchemy import func, select, text

from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    ProtectedTokenRegistry,
    TokenizedContent,
    TokenVaultEntry,
    VaultKeyVersion,
    VaultRotationJob,
)
from app.security.detect import contains_known_pii
from app.security.keyring import decrypt_vault_entry
from app.services.audit import verify_audit_chain
from app.services.workflow_audit import verify_workflow_chain
from seed.seed_data import RESET_TABLES


def main() -> None:
    settings = get_settings()
    if settings.database_backend != "postgresql":
        raise SystemExit("DATABASE_URL is not PostgreSQL/Supabase")

    with SessionLocal() as db:
        counts = {
            table: db.scalar(text(f"select count(*) from public.{table}"))
            for table in RESET_TABLES
        }
        rows = list(db.scalars(select(TokenizedContent)).all())
        amount_entries = list(
            db.scalars(
                select(TokenVaultEntry).where(TokenVaultEntry.entity_type == "AMOUNT")
            ).all()
        )
        registry_tokens = set(db.scalars(select(ProtectedTokenRegistry.token)).all())
        active_key_versions = list(
            db.scalars(
                select(VaultKeyVersion.version).where(VaultKeyVersion.status == "active")
            ).all()
        )
        incomplete_rotation_jobs = db.scalar(
            select(func.count())
            .select_from(VaultRotationJob)
            .where(VaultRotationJob.status != "completed")
        )
        unrotated_entries = (
            db.scalar(
                select(func.count())
                .select_from(TokenVaultEntry)
                .where(TokenVaultEntry.key_version != active_key_versions[0])
            )
            if len(active_key_versions) == 1
            else None
        )
        disclosure_chain_valid = verify_audit_chain(db)
        workflow_chain_valid = verify_workflow_chain(db)
        valid_decrypted_amounts = 0
        for entry in amount_entries:
            value = decrypt_vault_entry(db, entry)
            if re.fullmatch(r"RM \d{1,3}(?:,\d{3})*(?:\.\d{2})?", value):
                valid_decrypted_amounts += 1

    print("FinBrain Supabase row counts:")
    for table in RESET_TABLES:
        print(f"  {table}: {counts[table]}")
    print("Protected content by source/status:")
    for (source, status), count in sorted(
        Counter((row.source_system, row.processing_status) for row in rows).items()
    ):
        print(f"  {source}/{status}: {count}")
    actionable_rows = [
        row
        for row in rows
        if row.structured_summary and row.structured_summary.get("action_required")
    ]
    recurring = Counter(
        str(row.structured_summary.get("category")) for row in actionable_rows
    )
    print("Action-required categories:")
    for category, count in recurring.most_common():
        sources = sorted(
            {
                row.source_system
                for row in actionable_rows
                if str(row.structured_summary.get("category")) == category
            }
        )
        print(f"  {category}: {count} ({', '.join(sources)})")
    residual = sum(
        contains_known_pii(f"{row.content_text}\n{row.summary or ''}") for row in rows
    )
    print(f"Records with recognizable PII in protected content/summary: {residual}")

    protected_text = "\n".join(f"{row.content_text}\n{row.summary or ''}" for row in rows)
    amount_tokens = set(
        re.findall(r"AMOUNT_BAND_\d+_[0-9a-f]{10}", protected_text)
    )
    legacy_tokens = re.findall(r"AMOUNT_BAND_\d+(?!_[0-9a-f]{10})", protected_text)
    vault_tokens = {entry.token for entry in amount_entries}
    missing_vault_tokens = amount_tokens - vault_tokens
    invalid_vault_tokens = vault_tokens - set(
        token
        for token in vault_tokens
        if re.fullmatch(r"AMOUNT_BAND_\d+_[0-9a-f]{10}", token)
    )
    missing_registry_tokens = vault_tokens - registry_tokens

    print(f"Reversible amount tokens referenced: {len(amount_tokens)}")
    print(f"Encrypted amount vault entries: {len(amount_entries)}")
    print(f"Amount tokens missing vault entries: {len(missing_vault_tokens)}")
    print(f"Legacy band-only amount tokens: {len(legacy_tokens)}")
    print(f"Vault tokens missing safe registry metadata: {len(missing_registry_tokens)}")
    print(f"Active vault key generations: {len(active_key_versions)}")
    print(f"Incomplete vault rotation jobs: {incomplete_rotation_jobs}")
    print(f"Vault rows outside the active generation: {unrotated_entries}")
    print(f"Disclosure audit chain valid: {disclosure_chain_valid}")
    print(f"Workflow audit chain valid: {workflow_chain_valid}")
    print(
        "Normalized amount vault values: "
        f"{valid_decrypted_amounts}/{len(amount_entries)}"
    )

    failures = []
    if residual:
        failures.append("protected content contains recognizable PII")
    if missing_vault_tokens:
        failures.append("protected amount tokens are missing vault entries")
    if legacy_tokens or invalid_vault_tokens:
        failures.append("legacy or malformed amount tokens remain")
    if valid_decrypted_amounts != len(amount_entries):
        failures.append("amount vault entries are not normalized or decryptable")
    if missing_registry_tokens:
        failures.append("vault entries are missing safe registry metadata")
    if len(active_key_versions) != 1:
        failures.append("exactly one active vault key generation is required")
    if incomplete_rotation_jobs:
        failures.append("a vault rotation job is incomplete")
    if unrotated_entries:
        failures.append("vault rows remain outside the active generation")
    if not disclosure_chain_valid or not workflow_chain_valid:
        failures.append("an audit hash chain is invalid")
    if failures:
        raise SystemExit("Supabase demo-data check failed: " + "; ".join(failures))


if __name__ == "__main__":
    main()
