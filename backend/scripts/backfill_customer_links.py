from sqlalchemy import select

from app.db import SessionLocal
from app.models import EInvoiceRecord, TokenizedContent
from app.services.entity_resolution import (
    link_record_from_known_aliases,
    register_structured_customer_aliases,
)


def main() -> None:
    with SessionLocal() as db:
        aliases = links = 0
        records = db.scalars(
            select(EInvoiceRecord).where(EInvoiceRecord.buyer_customer_id.is_not(None))
        ).all()
        from app.models import Customer
        for record in records:
            customer = db.get(Customer, record.buyer_customer_id)
            if customer and record.buyer_name:
                aliases += len(register_structured_customer_aliases(
                    db, customer, record.buyer_name, source_system="einvoice",
                    source_record_id=record.source_record_id or f"einvoice:{record.id}",
                ))
        db.commit()
        for row in db.scalars(select(TokenizedContent)).all():
            links += len(link_record_from_known_aliases(db, row))
        print(
            "Customer identity backfill complete: "
            f"{aliases} aliases considered, {links} links created."
        )


if __name__ == "__main__":
    main()
