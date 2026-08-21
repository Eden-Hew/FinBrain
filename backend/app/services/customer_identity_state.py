from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, CustomerIdentityClaim


def reconcile_customer_identity_state(db: Session, customer: Customer) -> bool:
    """Repair stale cached profile flags when the claim ledger is fully resolved.

    This is intentionally one-way: it confirms a customer only when the primary
    identity is accepted and no unresolved claims remain. It never clears a real
    conflict or chooses a name on the user's behalf.
    """
    if customer.primary_name_token is None:
        return False

    accepted_primary = db.scalar(
        select(CustomerIdentityClaim.id)
        .where(
            CustomerIdentityClaim.tenant_id == customer.tenant_id,
            CustomerIdentityClaim.customer_id == customer.id,
            CustomerIdentityClaim.identity_token == customer.primary_name_token,
            CustomerIdentityClaim.status == "accepted",
        )
        .limit(1)
    )
    unresolved_claim = db.scalar(
        select(CustomerIdentityClaim.id)
        .where(
            CustomerIdentityClaim.tenant_id == customer.tenant_id,
            CustomerIdentityClaim.customer_id == customer.id,
            CustomerIdentityClaim.status.in_(("observed", "conflicting")),
        )
        .limit(1)
    )
    if accepted_primary is None or unresolved_claim is not None:
        return False

    changed = (
        customer.identity_review_status != "clear"
        or customer.profile_status != "confirmed"
    )
    customer.identity_review_status = "clear"
    customer.profile_status = "confirmed"
    return changed
