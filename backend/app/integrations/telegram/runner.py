import asyncio
import logging
from datetime import UTC, datetime

from telegram import Update

from app.config import get_settings
from app.db import SessionLocal, initialize_local_schema, set_worker_context
from app.integrations.telegram.bot import build_application
from app.integrations.telegram.drafts import draft_store
from app.integrations.telegram.sender import dispatch_one
from app.security.detect import warm_detector
from app.services.health import write_heartbeat
from app.services.overdue_reminders import plan_due_reminders


def _write_status(
    status: str,
    detector_ready: bool,
    failure_code: str | None = None,
    started_at: datetime | None = None,
    reset_started_at: bool = False,
) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        write_heartbeat(
            db,
            key="telegram",
            instance_id=settings.effective_service_instance_id,
            status=status,
            mode="polling",
            detector_ready=detector_ready,
            failure_code=failure_code,
            started_at=started_at,
            reset_started_at=reset_started_at,
        )


async def _heartbeat(detector_ready: bool) -> None:
    interval = get_settings().telegram_heartbeat_seconds
    while True:
        await asyncio.to_thread(
            _write_status,
            "healthy" if detector_ready else "degraded",
            detector_ready,
            None if detector_ready else "detector_unavailable",
        )
        await asyncio.sleep(interval)


async def _reminder_loop(bot) -> None:
    settings = get_settings()
    while True:
        try:
            with SessionLocal() as db:
                set_worker_context(
                    db,
                    actor_ref="overdue-reminders-worker",
                    tenant_id=settings.telegram_customer_tenant_id,
                )
                plan_due_reminders(
                    db, settings.telegram_customer_tenant_id, datetime.now(UTC).date()
                )
        except Exception:
            logging.getLogger(__name__).exception("telegram_reminder_loop_failed")
        await asyncio.sleep(settings.telegram_reminder_interval_seconds)


async def _outbound_loop(bot) -> None:
    settings = get_settings()
    while True:
        try:
            with SessionLocal() as db:
                set_worker_context(
                    db,
                    actor_ref="telegram-outbound-worker",
                    tenant_id=settings.telegram_customer_tenant_id,
                )
                for _ in range(settings.telegram_outbound_batch_size):
                    if await dispatch_one(db, bot) is None:
                        break
        except Exception:
            logging.getLogger(__name__).exception("telegram_outbound_loop_failed")
        await asyncio.sleep(settings.telegram_outbound_interval_seconds)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    initialize_local_schema()
    started_at = datetime.now(UTC)
    _write_status("starting", False, started_at=started_at, reset_started_at=True)
    detector = warm_detector()
    if not detector.loaded:
        _write_status("degraded", False, detector.failure_code or "detector_unavailable")
    application = build_application()

    original_post_init = application.post_init

    async def start_tasks(app) -> None:
        if original_post_init:
            await original_post_init(app)
        app.bot_data["heartbeat_task"] = asyncio.create_task(
            _heartbeat(detector.loaded), name="telegram-heartbeat"
        )
        if settings.telegram_outbound_enabled:
            app.bot_data["reminder_task"] = asyncio.create_task(
                _reminder_loop(app.bot), name="telegram-reminders"
            )
            app.bot_data["outbound_task"] = asyncio.create_task(
                _outbound_loop(app.bot), name="telegram-outbound"
            )

    application.post_init = start_tasks
    try:
        application.run_polling(
            allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY],
            drop_pending_updates=False,
        )
    finally:
        draft_store.clear()
        try:
            _write_status("stopped", detector.loaded)
        except Exception:
            pass


if __name__ == "__main__":
    main()
