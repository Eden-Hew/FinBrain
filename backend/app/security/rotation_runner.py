import time
from datetime import UTC, datetime

from app.config import get_settings
from app.db import SessionLocal, set_worker_context
from app.security.rotation import rotate_if_due
from app.services.health import write_heartbeat


def main() -> None:
    settings = get_settings()
    if not settings.vault_auto_rotation_enabled:
        print("Vault rotation worker disabled.")
        return
    print("Vault rotation worker started.")
    started_at = datetime.now(UTC)
    first_heartbeat = True
    while True:
        try:
            with SessionLocal() as db:
                set_worker_context(db)
                write_heartbeat(
                    db,
                    key="vault-rotation",
                    instance_id=settings.effective_service_instance_id,
                    status="healthy",
                    mode="scheduled",
                    started_at=started_at,
                    reset_started_at=first_heartbeat,
                )
                first_heartbeat = False
        except Exception:
            print("vault_rotation_heartbeat_failed")
        with SessionLocal() as db:
            set_worker_context(db)
            job = rotate_if_due(db)
            if job is not None:
                print(
                    f"Vault rotation completed: v{job.from_version} -> "
                    f"v{job.to_version}; rows={job.rows_rotated}"
                )
        time.sleep(settings.vault_rotation_check_seconds)


if __name__ == "__main__":
    main()
