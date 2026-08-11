from app.db import SessionLocal, engine
from app.models import Base
from app.services.ingestion import ingest_record
from seed.sample_records import SAMPLE_RECORDS


def run() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for index, record in enumerate(SAMPLE_RECORDS):
            sanitized = ingest_record(db, f"seed-{index}", record["source_type"], record["text"])
            print(f"seeded seed-{index}: {sanitized}")


if __name__ == "__main__":
    run()
