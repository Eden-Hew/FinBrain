"""Write the current tail hash of every tenant's audit/workflow chain to a JSON
file, committed to git by the anchor-audit-chain CI workflow. Git history is the
"separate, minimal-permission destination" from the roadmap: the credential that
pushes here (a GitHub Actions token) is entirely separate from the app's own
DATABASE_URL, so a compromised running app cannot silently rewrite yesterday's
anchor the way it could rewrite a Postgres row -- doing so would require a
force-push, an unmistakably visible act in the repository's history.

Usage: python -m scripts.anchor_audit_chains [output_path]
Defaults to audit-anchors/<UTC date>.json under the repository root.
"""

import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.db import SessionLocal
from app.services.audit_anchor import all_chain_anchors


def main() -> None:
    if get_settings().database_backend != "postgresql":
        raise SystemExit("DATABASE_URL is not PostgreSQL/Supabase")

    with SessionLocal() as db:
        anchors = all_chain_anchors(db)

    now = datetime.now(UTC)
    record = {
        "anchored_at": now.isoformat(timespec="seconds"),
        "anchors": [asdict(anchor) for anchor in anchors],
    }

    default_dir = Path(__file__).resolve().parents[2] / "audit-anchors"
    output_path = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else default_dir / f"{now.date().isoformat()}.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")

    print(f"Anchored {len(anchors)} chain(s) to {output_path}")
    print(json.dumps(record, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
