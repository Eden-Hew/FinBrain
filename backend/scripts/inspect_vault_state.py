from sqlalchemy import func, select

from app.config import get_settings
from app.db import SessionLocal
from app.models import TokenVaultEntry, VaultKeyVersion, VaultRotationJob


def main() -> None:
    if get_settings().database_backend != "postgresql":
        raise SystemExit("DATABASE_URL is not PostgreSQL/Supabase")
    with SessionLocal() as db:
        versions = list(db.scalars(select(VaultKeyVersion).order_by(VaultKeyVersion.version)).all())
        row_counts = dict(
            db.execute(
                select(TokenVaultEntry.key_version, func.count())
                .group_by(TokenVaultEntry.key_version)
                .order_by(TokenVaultEntry.key_version)
            ).all()
        )
        jobs = list(db.scalars(select(VaultRotationJob).order_by(VaultRotationJob.id)).all())
    print("Vault generations:")
    for version in versions:
        print(
            f"  v{version.version}: status={version.status}; "
            f"vault_rows={row_counts.get(version.version, 0)}"
        )
    print("Rotation jobs:")
    for job in jobs:
        print(
            f"  job {job.id}: v{job.from_version}->v{job.to_version}; "
            f"status={job.status}; rotated={job.rows_rotated}/{job.rows_total}"
        )


if __name__ == "__main__":
    main()
