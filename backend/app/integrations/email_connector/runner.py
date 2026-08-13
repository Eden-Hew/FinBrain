import logging
import time

from app.config import get_settings
from app.db import SessionLocal, initialize_local_schema
from app.integrations.email_connector.service import sync_mailbox


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.email_configured:
        raise RuntimeError("Email connector is not configured")
    initialize_local_schema()
    while True:
        try:
            with SessionLocal() as db:
                sync_mailbox(db)
        except Exception:
            logging.exception("email_sync_failed")
        time.sleep(settings.email_sync_interval_seconds)


if __name__ == "__main__":
    main()
