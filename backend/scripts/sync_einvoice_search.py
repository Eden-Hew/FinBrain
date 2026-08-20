from app.db import SessionLocal
from app.services.einvoice_readiness import sync_all_einvoice_tokenized_content


def main() -> None:
    with SessionLocal() as db:
        synced = sync_all_einvoice_tokenized_content(db)
    print(f"Synced {synced} e-invoice record(s) into protected search.")


if __name__ == "__main__":
    main()
