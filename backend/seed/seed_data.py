import argparse

from app.db import SessionLocal, engine
from app.models import Base
from app.schemas import CanonicalIngestionRecord
from app.services.ingestion import ingest_canonical_record
from seed.sample_records import SAMPLE_RECORDS


def adapt_seed_record(index: int, record: dict[str, str]) -> CanonicalIngestionRecord:
    """Convert the fixture format into the same contract future connectors must produce."""
    return CanonicalIngestionRecord(
        source_record_id=f"seed-{index}",
        source_system=record["source_type"],
        record_type=record["source_type"],
        text=record["text"],
        metadata={"dataset": "sample"},
    )


def run(*, refresh: bool = False) -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for index, record in enumerate(SAMPLE_RECORDS):
            result = ingest_canonical_record(db, adapt_seed_record(index, record), refresh=refresh)
            print(
                f"seeded {result.source_record_id} [{result.processing_status}]: "
                f"{result.content_text}"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed FinBrain through the protected pipeline.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Retokenize and re-embed existing seed records without deleting audit history.",
    )
    run(refresh=parser.parse_args().refresh)
