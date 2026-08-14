import argparse
from datetime import datetime

from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal, initialize_local_schema
from app.schemas import CanonicalIngestionRecord
from app.services.ingestion import ingest_canonical_record
from seed.sample_records import SAMPLE_RECORDS

RESET_TABLES = (
    "structured_ingestion_batches",
    "recommendation_decisions",
    "recommendation_evidence",
    "process_recommendations",
    "workflow_audit_log",
    "audit_log",
    "email_ingestion_receipts",
    "email_sync_state",
    "telegram_update_receipts",
    "integration_status",
    "token_vault",
    "tokenized_content",
)


def adapt_seed_record(record: dict) -> CanonicalIngestionRecord:
    """Convert a demo fixture into the canonical connector-neutral contract."""
    return CanonicalIngestionRecord(
        source_record_id=record["source_record_id"],
        source_system=record["source_system"],
        record_type=record["record_type"],
        text=record["text"],
        occurred_at=datetime.fromisoformat(record["occurred_at"]),
        metadata={"dataset": "track2_demo", **record.get("metadata", {})},
    )


def reset_demo_data() -> None:
    """Clear only FinBrain application rows while preserving schema, migrations, and RLS."""
    settings = get_settings()
    with SessionLocal() as db:
        if settings.database_backend == "postgresql":
            qualified = ", ".join(f"public.{table}" for table in RESET_TABLES)
            db.execute(text(f"truncate table {qualified} restart identity"))
        else:
            for table in RESET_TABLES:
                db.execute(text(f"delete from {table}"))
        db.commit()


def run(*, refresh: bool = False, reset: bool = False) -> None:
    initialize_local_schema()
    if reset:
        reset_demo_data()
        print("cleared FinBrain application data; schema and migrations preserved")
    with SessionLocal() as db:
        for record in SAMPLE_RECORDS:
            canonical = adapt_seed_record(record)
            result = ingest_canonical_record(db, canonical, refresh=refresh)
            print(
                f"seeded {canonical.source_system}/{result.source_record_id} "
                f"[{result.processing_status}] via {result.enrichment_mode or 'none'}"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed FinBrain through the protected pipeline.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Retokenize and re-embed existing seed records without deleting audit history.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all FinBrain application rows before inserting the clean demo dataset.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required confirmation for --reset.",
    )
    args = parser.parse_args()
    if args.reset and not args.yes:
        parser.error("--reset requires --yes because it deletes existing FinBrain application data")
    run(refresh=args.refresh, reset=args.reset)
