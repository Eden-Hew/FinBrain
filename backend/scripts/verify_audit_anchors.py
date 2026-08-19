"""Check every committed anchor file against the live chain: if a previously
anchored tail hash no longer exists in its tenant's chain, that segment of the
audit trail was altered or deleted after the anchor was taken. Run manually by
an operator, or on its own schedule slightly behind anchor_audit_chains.py.

Usage: python -m scripts.verify_audit_anchors [audit-anchors-dir]
Defaults to audit-anchors/ under the repository root.
"""

import json
import sys
from pathlib import Path

from app.config import get_settings
from app.db import SessionLocal
from app.services.audit_anchor import ChainAnchor, anchor_is_still_present


def main() -> None:
    if get_settings().database_backend != "postgresql":
        raise SystemExit("DATABASE_URL is not PostgreSQL/Supabase")

    anchors_dir = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parents[2] / "audit-anchors"
    )
    files = sorted(anchors_dir.glob("*.json"))
    if not files:
        print(f"No anchor files found under {anchors_dir}")
        return

    failures: list[str] = []
    with SessionLocal() as db:
        for path in files:
            record = json.loads(path.read_text())
            for entry in record["anchors"]:
                anchor = ChainAnchor(
                    tenant_id=entry["tenant_id"], chain=entry["chain"], tail_hash=entry["tail_hash"]
                )
                if not anchor_is_still_present(db, anchor):
                    failures.append(
                        f"{path.name}: {anchor.chain} chain for tenant "
                        f"{anchor.tenant_id or 'system'} no longer contains anchored hash "
                        f"{anchor.tail_hash}"
                    )

    print(f"Checked {len(files)} anchor file(s) against the live chain.")
    if failures:
        raise SystemExit(
            "Audit chain anchor verification failed -- possible tampering:\n"
            + "\n".join(failures)
        )
    print("All anchored hashes are still present. No tampering detected.")


if __name__ == "__main__":
    main()
