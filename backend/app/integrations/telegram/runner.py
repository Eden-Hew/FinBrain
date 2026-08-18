import asyncio
import logging
from datetime import UTC, datetime

from telegram import Update

from app.config import get_settings
from app.db import SessionLocal, initialize_local_schema
from app.integrations.telegram.bot import build_application
from app.integrations.telegram.drafts import draft_store
from app.security.detect import warm_detector
from app.services.health import write_heartbeat


def _write_status(
    status: str,
    detector_ready: bool,
    failure_code: str | None = None,
    started_at: datetime | None = None,
) -> None:
    with SessionLocal() as db:
        write_heartbeat(
            db,
            key="telegram",
            status=status,
            mode="polling",
            detector_ready=detector_ready,
            failure_code=failure_code,
            started_at=started_at,
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
    _write_status("starting", False, started_at=started_at)
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
