import argparse

from sqlalchemy import select

from app.db import SessionLocal, set_worker_context
from app.integrations.email_connector.identity import route_email_sender
from app.models import (
    DEFAULT_TENANT_ID,
    EmailIngestionReceipt,
    TokenizedContent,
)


def recover(source_record_id: str) -> int:
    with SessionLocal() as db:
        set_worker_context(
            db,
            actor_ref="email-profile-recovery",
            tenant_id=DEFAULT_TENANT_ID,
        )
        row = db.scalar(
            select(TokenizedContent).where(
                TokenizedContent.tenant_id == DEFAULT_TENANT_ID,
                TokenizedContent.source_system == "email",
                TokenizedContent.source_record_id == source_record_id,
            )
        )
        if row is None:
            raise SystemExit("Protected email record was not found.")
        receipt = db.scalar(
            select(EmailIngestionReceipt).where(
                EmailIngestionReceipt.source_record_id == source_record_id
            )
        )
        if receipt is None:
            raise SystemExit("Email ingestion receipt was not found.")
        customer_id = route_email_sender(db, receipt=receipt, protected_row=row)
        if customer_id is None:
            raise SystemExit("The protected email has no unique recoverable sender endpoint.")
        return customer_id


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create or link a customer profile for one protected email record."
    )
    parser.add_argument("source_record_id", help="Opaque email:* source record identifier")
    args = parser.parse_args()
    customer_id = recover(args.source_record_id)
    print(f"Protected email linked to customer {customer_id}.")


if __name__ == "__main__":
    main()
