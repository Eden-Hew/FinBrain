import logging
import time
from datetime import UTC, datetime

from app.config import get_settings
from app.db import SessionLocal, initialize_local_schema
from app.integrations.email_connector.service import sync_mailbox
from app.services.health import write_heartbeat


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.email_configured:
        raise RuntimeError("Email connector is not configured")
    initialize_local_schema()
    started_at = datetime.now(UTC)
    first_heartbeat = True
    while True:
        try:
            with SessionLocal() as db:
                write_heartbeat(
                    db,
                    key="email",
                    instance_id=settings.effective_service_instance_id,
                    status="healthy",
                    mode="imap",
                    started_at=started_at,
                    reset_started_at=first_heartbeat,
                )
                first_heartbeat = False
        except Exception:
            logging.exception("email_heartbeat_failed")
        try:
            with SessionLocal() as db:
                sync_mailbox(db)
        except Exception:
            logging.exception("email_sync_failed")
        time.sleep(settings.email_sync_interval_seconds)


if __name__ == "__main__":
    main()
