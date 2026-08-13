import re
from collections import Counter

from sqlalchemy import select, text

from app.config import get_settings
from app.db import SessionLocal
from app.models import TokenizedContent, TokenVaultEntry
from app.security.crypto import decrypt_value, derive_key
from app.security.detect import contains_known_pii
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
    valid_decrypted_amounts = 0
    for entry in amount_entries:
        value = decrypt_value(
            entry.encrypted_value,
            entry.nonce,
            derive_key(info=f"vault:{entry.token}".encode()),
        )
        if re.fullmatch(r"RM \d{1,3}(?:,\d{3})*(?:\.\d{2})?", value):
            valid_decrypted_amounts += 1

    print(f"Reversible amount tokens referenced: {len(amount_tokens)}")
    print(f"Encrypted amount vault entries: {len(amount_entries)}")
    print(f"Amount tokens missing vault entries: {len(missing_vault_tokens)}")
    print(f"Legacy band-only amount tokens: {len(legacy_tokens)}")
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
    if failures:
        raise SystemExit("Supabase demo-data check failed: " + "; ".join(failures))


if __name__ == "__main__":
    main()
