from app.db import SessionLocal, set_worker_context
from app.security.rotation import run_rotation


def main() -> None:
    with SessionLocal() as db:
        set_worker_context(db)
        job = run_rotation(db)
    print(
        f"Vault rotation passed: v{job.from_version} -> v{job.to_version}; "
        f"rows={job.rows_rotated}"
    )


if __name__ == "__main__":
    main()
