import argparse

from app.db import SessionLocal, engine
from app.models import Base
from app.services.ingestion import ingest_record
from seed.sample_records import SAMPLE_RECORDS


def run(*, refresh: bool = False) -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for index, record in enumerate(SAMPLE_RECORDS):
            sanitized = ingest_record(
                db,
                f"seed-{index}",
                record["source_type"],
                record["text"],
                refresh=refresh,
            )
            print(f"seeded seed-{index}: {sanitized}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed FinBrain through the protected pipeline.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Retokenize and re-embed existing seed records without deleting audit history.",
    )
    run(refresh=parser.parse_args().refresh)
