from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select

from app.db import SessionLocal, initialize_local_schema, set_rls_context
from app.models import (
    DEFAULT_TENANT_ID,
    CustomerRecordLink,
    EInvoiceRecord,
    TokenizedContent,
)
from app.schemas import CanonicalIngestionRecord
from app.services.customer_attention import recalculate_customer_attention
from app.services.einvoice_readiness import sync_einvoice_tokenized_content
from app.services.entity_resolution import (
    register_structured_customer_aliases,
    resolve_customer,
)
from app.services.ingestion import ingest_canonical_record
from app.services.outreach import register_email_endpoint

CUSTOMER_NAME = "Luma Retail Sdn Bhd"
CUSTOMER_EMAIL = "aisha.karim@luma-retail.example"
INVOICE_NUMBER = "LUMA-INV-3001"
SOURCE_RECORD_ID = "demo:customer:luma:email:001"
DEMO_OWNER_ID = "30000000-0000-0000-0000-000000000004"


def _ensure_verified_link(
    db, *, customer_id: int, content_id: int, alias_id: int, basis: str
) -> None:
    existing = db.scalar(
        select(CustomerRecordLink).where(
            CustomerRecordLink.tenant_id == DEFAULT_TENANT_ID,
            CustomerRecordLink.customer_id == customer_id,
            CustomerRecordLink.tokenized_content_id == content_id,
            CustomerRecordLink.match_basis == basis,
        )
    )
    if existing is None:
        db.add(
            CustomerRecordLink(
                tenant_id=DEFAULT_TENANT_ID,
                customer_id=customer_id,
                tokenized_content_id=content_id,
                alias_id=alias_id,
                match_status="verified",
                confidence=1.0,
                match_basis=basis,
            )
        )
        db.commit()


def main() -> None:
    """Add one idempotent, non-destructive customer-outreach demonstration fixture."""
    initialize_local_schema()
    with SessionLocal() as db:
        set_rls_context(
            db,
            user_id=DEMO_OWNER_ID,
            user_role="owner_director",
            actor_ref="demo-customer-seed",
            tenant_id=DEFAULT_TENANT_ID,
        )
        customer = resolve_customer(db, DEFAULT_TENANT_ID, CUSTOMER_NAME)
        if customer is None:
            raise RuntimeError("demo_customer_resolution_failed")
        aliases = register_structured_customer_aliases(
            db,
            customer,
            CUSTOMER_NAME,
            source_system="demo_seed",
            source_record_id=SOURCE_RECORD_ID,
        )
        organization_alias = next(row for row in aliases if row.alias_type == "ORG")
        db.commit()

        invoice = db.scalar(
            select(EInvoiceRecord).where(
                EInvoiceRecord.tenant_id == DEFAULT_TENANT_ID,
                EInvoiceRecord.invoice_no == INVOICE_NUMBER,
            )
        )
        if invoice is None:
            invoice = EInvoiceRecord(
                tenant_id=DEFAULT_TENANT_ID,
                supplier_name="FinBrain Demo Supplier Sdn Bhd",
                supplier_tin="C2026082001",
                buyer_name=CUSTOMER_NAME,
                buyer_customer_id=customer.id,
                invoice_no=INVOICE_NUMBER,
                issue_date=date(2026, 8, 12),
                due_date=date(2026, 8, 18),
                currency="MYR",
                tax_type="SST",
                tax_rate="6%",
                total_amount=Decimal("3250.00"),
                status="validated",
                uin="MY29ALUMA01",
            )
            db.add(invoice)
            db.commit()
        elif invoice.buyer_customer_id != customer.id:
            invoice.buyer_customer_id = customer.id
            db.commit()
        sync_einvoice_tokenized_content(db, invoice)
        invoice_content = db.scalar(
            select(TokenizedContent).where(
                TokenizedContent.source_record_id == f"einvoice:{invoice.id}"
            )
        )
        if invoice_content is None:
            raise RuntimeError("demo_customer_invoice_content_missing")
        _ensure_verified_link(
            db,
            customer_id=customer.id,
            content_id=invoice_content.id,
            alias_id=organization_alias.id,
            basis="structured_customer_fixture",
        )

        ingest_canonical_record(
            db,
            CanonicalIngestionRecord(
                source_record_id=SOURCE_RECORD_ID,
                source_system="email",
                record_type="customer_email",
                occurred_at=datetime.fromisoformat("2026-08-19T10:15:00+08:00"),
                tenant_id=DEFAULT_TENANT_ID,
                text=(
                    "Subject: Delivery shortage for LUMA-INV-3001\n"
                    "Aisha Karim from Luma Retail Sdn Bhd reports that invoice "
                    "LUMA-INV-3001 for RM3,250 covers ten units, but only eight arrived. "
                    "The issue needs a finance owner and a delivery reconciliation today. "
                    "Contact aisha.karim@luma-retail.example."
                ),
                metadata={"dataset": "customer_outreach_demo", "business_unit": "finance_ops"},
            ),
        )
        email_content = db.scalar(
            select(TokenizedContent).where(TokenizedContent.source_record_id == SOURCE_RECORD_ID)
        )
        if email_content is None:
            raise RuntimeError("demo_customer_email_content_missing")
        _ensure_verified_link(
            db,
            customer_id=customer.id,
            content_id=email_content.id,
            alias_id=organization_alias.id,
            basis="structured_customer_fixture",
        )

        endpoint = register_email_endpoint(
            db,
            tenant_id=DEFAULT_TENANT_ID,
            customer_id=customer.id,
            value=CUSTOMER_EMAIL,
        )
        snapshot = recalculate_customer_attention(db, DEFAULT_TENANT_ID, customer.id)
        print(f"Customer: {CUSTOMER_NAME} (id={customer.id})")
        print(f"Invoice: {INVOICE_NUMBER} (id={invoice.id})")
        print(f"Protected endpoint: {endpoint.endpoint_token} ({endpoint.verification_status})")
        print(f"Attention: {snapshot.score}/100 ({snapshot.priority})")
        print("Demo customer preparation passed.")


if __name__ == "__main__":
    main()
