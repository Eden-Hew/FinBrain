import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.config import Settings

_RESERVED_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message"}


class JsonFormatter(logging.Formatter):
    """Single-line JSON log records, ingestible by any log aggregator without parsing rules."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        extras = {
            key: value for key, value in record.__dict__.items() if key not in _RESERVED_ATTRS
        }
        if extras:
            payload["extra"] = extras
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    # Route uvicorn's own loggers through the same structured handler instead of
    # letting them keep their default plain-text formatter.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True


def init_sentry(settings: Settings) -> None:
    """No-op unless SENTRY_DSN is set; lazy import so the SDK is only ever touched when used.

    send_default_pii is explicitly False: this app's whole design is protecting PII behind
    tokens, and Sentry's default PII capture (request bodies, local variables in stack
    frames) would work directly against that. Enabling richer capture must be a deliberate,
    reviewed decision, not a default.
    """
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
    )
