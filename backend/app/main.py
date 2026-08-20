import logging
import uuid
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db, initialize_local_schema
from app.observability import configure_logging, init_sentry
from app.routes import (
    audit_log,
    auth,
    conversations,
    customers,
    einvoice,
    finance,
    health,
    ingestion,
    integrations,
    privacy,
    query,
    query_artifacts,
    recommendations,
    uploads,
)
from app.security.detect import warm_detector

settings = get_settings()
configure_logging(settings.log_level)
init_sentry(settings)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_local_schema()
    if settings.prewarm_gliner_on_startup and settings.enable_gliner:
        detector = warm_detector()
        logger.info(
            "startup_detector_warm_complete",
            extra={
                "loaded": detector.loaded,
                "device": detector.device,
                "failure_code": detector.failure_code,
            },
        )
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "http_request_failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "duration_ms": round((perf_counter() - started) * 1_000, 1),
            },
        )
        raise
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "http_request_completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((perf_counter() - started) * 1_000, 1),
        },
    )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-FinBrain-Filename",
        "X-FinBrain-Record-Type",
        "X-FinBrain-Preview-Digest",
        "X-Request-ID",
    ],
    expose_headers=["X-Request-ID"],
)
app.include_router(auth.router)
app.include_router(query.router)
app.include_router(query_artifacts.router)
app.include_router(audit_log.router)
app.include_router(ingestion.router)
app.include_router(integrations.router)
app.include_router(recommendations.router)
app.include_router(einvoice.router)
app.include_router(finance.router)
app.include_router(uploads.router)
app.include_router(conversations.router)
app.include_router(customers.router)
app.include_router(privacy.router)
app.include_router(health.router)


@app.get("/health", tags=["system"])
def health(response: Response, db: Session = Depends(get_db)) -> dict[str, str | bool]:
    try:
        db.execute(text("select 1"))
        database_reachable = True
    except Exception:
        logger.exception("health_check_database_unreachable")
        database_reachable = False
    if not database_reachable:
        response.status_code = 503
    return {
        "status": "ok" if database_reachable else "degraded",
        "database_reachable": database_reachable,
        "mode": (
            "morpheus"
            if settings.morpheus_api_key
            else "gemini"
            if settings.gemini_api_key
            else "offline-demo"
        ),
        "database": settings.database_backend,
        "gliner_enabled": settings.enable_gliner,
        "ocr_enabled": settings.enable_ocr,
        "production_secret_configured": settings.production_secret_configured,
    }
