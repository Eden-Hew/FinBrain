from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import initialize_local_schema
from app.routes import (
    audit_log,
    auth,
    conversations,
    health,
    ingestion,
    integrations,
    query,
    query_artifacts,
    recommendations,
    uploads,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_local_schema()
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
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
    ],
)
app.include_router(auth.router)
app.include_router(query.router)
app.include_router(query_artifacts.router)
app.include_router(audit_log.router)
app.include_router(ingestion.router)
app.include_router(integrations.router)
app.include_router(recommendations.router)
app.include_router(uploads.router)
app.include_router(conversations.router)
app.include_router(health.router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
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
