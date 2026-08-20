import logging
import time
from datetime import UTC, datetime

from app.config import get_settings
from app.db import SessionLocal, initialize_local_schema, set_worker_context
from app.integrations.email_connector.sender import dispatch_pending, recover_stale_sends
from app.integrations.email_connector.service import sync_mailbox
from app.models import DEFAULT_TENANT_ID
from app.services.health import write_heartbeat


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.email_worker_configured:
        raise RuntimeError("Email worker is not configured")
    initialize_local_schema()
    started_at = datetime.now(UTC)
    first_heartbeat = True
    while True:
        try:
            with SessionLocal() as db:
                set_worker_context(
                    db, actor_ref="email-worker", tenant_id=DEFAULT_TENANT_ID
                )
                write_heartbeat(
                    db,
                    key="email",
                    instance_id=settings.effective_service_instance_id,
                    status="healthy",
                    mode=("imap+smtp" if settings.email_smtp_configured else "imap"),
                    started_at=started_at,
                    reset_started_at=first_heartbeat,
                )
                first_heartbeat = False
        except Exception:
            logging.exception("email_heartbeat_failed")
        if settings.email_configured:
            try:
                with SessionLocal() as db:
                    set_worker_context(
                        db, actor_ref="email-worker", tenant_id=DEFAULT_TENANT_ID
                    )
                    sync_mailbox(db)
            except Exception:
                logging.exception("email_sync_failed")
        try:
            if settings.email_smtp_configured:
                with SessionLocal() as db:
                    set_worker_context(
                        db, actor_ref="email-worker", tenant_id=DEFAULT_TENANT_ID
                    )
                    recover_stale_sends(db)
                    dispatch_pending(db)
        except Exception:
            logging.exception("email_outbound_failed")
        time.sleep(settings.email_sync_interval_seconds)


if __name__ == "__main__":
    main()
