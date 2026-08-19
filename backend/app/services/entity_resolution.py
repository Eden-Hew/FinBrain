import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer

_CORPORATE_SUFFIXES = re.compile(
    r"\b(SDN\.?\s*BHD\.?|BERHAD|ENTERPRISE|TRADING|PLT|LTD\.?|LLC)\b", re.IGNORECASE
)


def normalize_business_name(name: str) -> str:
    """Collapse corporate-suffix and casing/punctuation variants of a business name
    to one comparable key, e.g. "Acme Sdn Bhd" and "ACME SDN. BHD." both become
    "ACME" -- so records referring to the same real-world entity link together even
    when the name was typed slightly differently across sources.
    """
    without_suffix = _CORPORATE_SUFFIXES.sub("", name)
    return re.sub(r"[^A-Z0-9]", "", without_suffix.upper())


def resolve_customer(db: Session, tenant_id: str, name: str) -> Customer | None:
    """Find-or-create the canonical Customer row for a business name within one tenant.

    Returns None when the name normalizes to nothing usable (blank, or entirely
    punctuation/corporate-suffix boilerplate) rather than creating a garbage
    all-tenants-collide-on-"" customer row.
    """
    normalized = normalize_business_name(name)
    if not normalized:
        return None
    existing = db.scalar(
        select(Customer).where(
            Customer.tenant_id == tenant_id, Customer.normalized_name == normalized
        )
    )
    if existing is not None:
        return existing
    customer = Customer(tenant_id=tenant_id, canonical_name=name, normalized_name=normalized)
    db.add(customer)
    db.flush()
    return customer
