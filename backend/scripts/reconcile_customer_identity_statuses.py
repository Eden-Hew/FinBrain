import argparse

from sqlalchemy import select

from app.db import SessionLocal, initialize_local_schema, set_worker_context
from app.models import DEFAULT_TENANT_ID, Customer
from app.services.customer_identity_state import reconcile_customer_identity_state
from app.services.workflow_audit import write_workflow_event


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair stale customer status flags from resolved identity claims."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit repairs. Without this flag the command is a dry run.",
    )
    args = parser.parse_args()

    initialize_local_schema()
    with SessionLocal() as db:
        set_worker_context(
            db,
            actor_ref="identity-state-reconciliation",
            tenant_id=DEFAULT_TENANT_ID,
        )
        customers = db.scalars(
            select(Customer).where(Customer.tenant_id == DEFAULT_TENANT_ID)
        ).all()
        changed = [
            customer
            for customer in customers
            if reconcile_customer_identity_state(db, customer)
        ]

        mode = "apply" if args.apply else "dry-run"
        print(f"Identity reconciliation ({mode}): {len(changed)} customer(s).")
        for customer in changed:
            print(f"- customer_id={customer.id}: confirmed / clear")

        if not args.apply:
            db.rollback()
            return

        for customer in changed:
            write_workflow_event(
                db,
                event_type="customer_identity_state_reconciled",
                actor_role="system_worker",
                actor_ref="identity-state-reconciliation",
                resource_type="customer",
                resource_id=str(customer.id),
                tenant_id=customer.tenant_id,
                event_payload={
                    "profile_status": "confirmed",
                    "identity_review_status": "clear",
                },
            )
        db.commit()


if __name__ == "__main__":
    main()
