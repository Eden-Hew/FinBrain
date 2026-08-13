import asyncio
from collections.abc import Awaitable, Callable

from app.config import get_settings
from app.db import SessionLocal
from app.models import IntegrationStatus, utcnow
from app.schemas import CanonicalIngestionRecord, IngestionResult
from app.services.ingestion import enrich_protected_record, protect_canonical_record

_semaphore: asyncio.Semaphore | None = None


def protect(record: CanonicalIngestionRecord) -> IngestionResult:
    with SessionLocal() as db:
        result = protect_canonical_record(db, record)
        status = db.get(IntegrationStatus, "telegram")
        if status:
            status.last_update_at = utcnow()
            db.commit()
        return result


def enrich(source_record_id: str) -> IngestionResult:
    with SessionLocal() as db:
        return enrich_protected_record(db, source_record_id)


async def enrich_in_background(
    source_record_id: str,
    notify: Callable[[IngestionResult], Awaitable[None]],
) -> None:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_settings().telegram_enrichment_concurrency)
    async with _semaphore:
        result = await asyncio.to_thread(enrich, source_record_id)
        await notify(result)
