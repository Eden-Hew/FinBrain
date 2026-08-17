import time

from app.config import get_settings
from app.db import SessionLocal, set_worker_context
from app.security.rotation import rotate_if_due


def main() -> None:
    settings = get_settings()
    if not settings.vault_auto_rotation_enabled:
        print("Vault rotation worker disabled.")
        return
    print("Vault rotation worker started.")
    while True:
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
