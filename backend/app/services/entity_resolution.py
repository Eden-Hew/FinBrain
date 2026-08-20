import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, CustomerAlias, CustomerRecordLink, TokenizedContent
from app.security.detokenize import TOKEN_PATTERN
from app.security.tokenize import derive_token

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


def register_structured_customer_aliases(
    db: Session,
    customer: Customer,
    raw_name: str,
    *,
    source_system: str,
    source_record_id: str | None = None,
) -> list[CustomerAlias]:
    """Register only deterministic tokens; the supplied raw name is never stored here."""
    rows: list[CustomerAlias] = []
    for alias_type in ("ORG", "PERSON"):
        token = derive_token(alias_type, raw_name, customer.tenant_id)
        row = db.scalar(
            select(CustomerAlias).where(
                CustomerAlias.tenant_id == customer.tenant_id,
                CustomerAlias.customer_id == customer.id,
                CustomerAlias.alias_token == token,
            )
        )
        if row is None:
            row = CustomerAlias(
                tenant_id=customer.tenant_id,
                customer_id=customer.id,
                alias_token=token,
                alias_type=alias_type,
                match_status="verified",
                confidence=1.0,
                source_system=source_system,
                source_record_id=source_record_id,
            )
            db.add(row)
            db.flush()
        rows.append(row)
    return rows


def link_record_from_known_aliases(
    db: Session, row: TokenizedContent
) -> list[CustomerRecordLink]:
    tokens = set(TOKEN_PATTERN.findall(row.content_text))
    for value in row.safe_metadata.values():
        if isinstance(value, str):
            tokens.update(TOKEN_PATTERN.findall(value))
    if not tokens:
        return []
    aliases = db.scalars(
        select(CustomerAlias).where(
            CustomerAlias.tenant_id == row.tenant_id,
            CustomerAlias.alias_token.in_(tokens),
            CustomerAlias.match_status.in_(("verified", "probable", "ambiguous")),
        )
    ).all()
    links: list[CustomerRecordLink] = []
    for alias in aliases:
        link = db.scalar(
            select(CustomerRecordLink).where(
                CustomerRecordLink.tenant_id == row.tenant_id,
                CustomerRecordLink.customer_id == alias.customer_id,
                CustomerRecordLink.tokenized_content_id == row.id,
                CustomerRecordLink.match_basis == "exact_protected_alias",
            )
        )
        if link is None:
            link = CustomerRecordLink(
                tenant_id=row.tenant_id,
                customer_id=alias.customer_id,
                tokenized_content_id=row.id,
                alias_id=alias.id,
                match_status=alias.match_status,
                confidence=alias.confidence,
                match_basis="exact_protected_alias",
            )
            db.add(link)
            links.append(link)
    db.commit()
    return links


def review_link(
    db: Session, link: CustomerRecordLink, *, decision: str, reviewer_id: str
) -> CustomerRecordLink:
    if decision not in {"verified", "rejected"}:
        raise ValueError("unsupported_identity_decision")
    link.match_status = decision
    link.reviewed_by_user_id = reviewer_id
    link.reviewed_at = datetime.now(UTC)
    db.commit()
    return link
