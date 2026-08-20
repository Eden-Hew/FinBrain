from sqlalchemy import select

from app.db import SessionLocal
from app.models import Customer
from app.services.customer_attention import recalculate_customer_attention


def main() -> None:
    with SessionLocal() as db:
        customers = db.scalars(select(Customer)).all()
        for customer in customers:
            recalculate_customer_attention(db, customer.tenant_id, customer.id)
        print(f"Recalculated attention for {len(customers)} customer(s).")


if __name__ == "__main__":
    main()
