import html
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.services.health import BACKEND_STARTED_AT, heartbeat_rows, uptime_seconds

router = APIRouter(tags=["system"])


def _format_uptime(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86_400)
    hours, seconds = divmod(seconds, 3_600)
    minutes, _ = divmod(seconds, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _format_time(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _row_service(db: Session) -> list[dict]:
    settings = get_settings()
    rows = heartbeat_rows(db)

    def build(key, label, configured, mode, stale_seconds):
        row = rows.get(key)
        status = "disabled"
        started_at = None
        heartbeat = None
        detector_ready = False
        failure_code = None
        if row is not None:
            status = row.status
            started_at = row.started_at
            heartbeat = row.last_heartbeat_at
            detector_ready = row.detector_ready
            failure_code = row.failure_code
            if heartbeat is not None:
                heartbeat_tz = (
                    heartbeat if heartbeat.tzinfo is not None else heartbeat.replace(tzinfo=UTC)
                )
                if (datetime.now(UTC) - heartbeat_tz).total_seconds() > stale_seconds:
                    status = "offline"
        return {
            "key": key,
            "label": label,
            "configured": configured,
            "status": status,
            "mode": mode,
            "started_at": started_at,
            "last_heartbeat_at": heartbeat,
            "detector_ready": detector_ready,
            "failure_code": failure_code,
        }

    return [
        build("telegram", "Telegram worker", bool(settings.telegram_bot_token), "polling",
              max(settings.telegram_heartbeat_seconds * 3, 90)),
        build("email", "Email worker", settings.email_configured, "imap",
              max(settings.email_sync_interval_seconds * 3, 90)),
        build("vault-rotation", "Vault rotation worker",
              settings.vault_auto_rotation_enabled, "scheduled",
              max(settings.vault_rotation_check_seconds * 3, 90)),
    ]


@router.get("/status", response_class=HTMLResponse)
def status_page(db: Session = Depends(get_db)) -> HTMLResponse:
    settings = get_settings()
    workers = _row_service(db)
    backend_uptime = uptime_seconds(BACKEND_STARTED_AT)

    rows = []
    rows.append(_service_html(
        "backend", "Backend API", True, "healthy", settings.database_backend,
        BACKEND_STARTED_AT, datetime.now(UTC), True, None,
    ))
    for worker in workers:
        rows.append(_service_html(
            worker["key"], worker["label"], worker["configured"], worker["status"],
            worker["mode"], worker["started_at"], worker["last_heartbeat_at"],
            worker["detector_ready"], worker["failure_code"],
        ))

    return HTMLResponse(
        "<!doctype html>"
        "<html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<meta http-equiv='refresh' content='10'>"
        "<title>FinBrain service status</title>"
        "<style>"
        "body{font-family:system-ui,sans-serif;margin:2rem;background:#0f172a;color:#e2e8f0}"
        "h1{font-size:1.4rem}table{border-collapse:collapse;width:100%;max-width:900px;margin-top:1rem}"
        "th,td{text-align:left;padding:.6rem .8rem;border-bottom:1px solid #334155}"
        ".up{color:#4ade80}.down{color:#f87171}.disabled{color:#64748b}.starting{color:#facc15}.degraded{color:#facc15}"
        "code{background:#1e293b;padding:.1rem .3rem;border-radius:4px}"
        "</style></head><body>"
        "<h1>FinBrain service status</h1>"
        "<p>Backend uptime: <strong>" + _format_uptime(backend_uptime) + "</strong></p>"
        "<table><thead><tr><th>Service</th><th>Status</th><th>Uptime</th><th>Started</th>"
        "<th>Last heartbeat</th><th>Mode</th><th>Failure</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></body></html>"
    )


def _service_html(
    key: str,
    label: str,
    configured: bool,
    status: str,
    mode: str,
    started_at: datetime | None,
    heartbeat: datetime | None,
    detector_ready: bool,
    failure_code: str | None,
) -> str:
    if not configured:
        css = "disabled"
        shown_status = "disabled"
        uptime = "—"
    else:
        shown_status = status
        if status == "offline":
            css = "down"
        elif status == "healthy":
            css = "up"
        elif status in {"starting", "degraded"}:
            css = "starting" if status == "starting" else "degraded"
        else:
            css = "down"
        uptime = _format_uptime(uptime_seconds(started_at))
    failure = html.escape(str(failure_code)) if failure_code else "—"
    return (
        f"<tr><td>{html.escape(label)}</td>"
        f"<td class='{css}'>{html.escape(shown_status)}</td>"
        f"<td>{uptime}</td>"
        f"<td>{_format_time(started_at)}</td>"
        f"<td>{_format_time(heartbeat)}</td>"
        f"<td>{html.escape(mode)}</td>"
        f"<td>{failure}</td></tr>"
    )
