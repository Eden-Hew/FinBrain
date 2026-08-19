import argparse
from datetime import date, datetime
import secrets

from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal, initialize_local_schema
from app.models import EInvoiceRecord
from app.schemas import CanonicalIngestionRecord
from app.services.ingestion import ingest_canonical_record
from seed.sample_records import SAMPLE_RECORDS

RESET_TABLES = (
    "conversation_turn_citations",
    "conversation_turns",
    "conversations",
    "structured_ingestion_batches",
    "recommendation_decisions",
    "recommendation_evidence",
    "process_recommendations",
    "einvoice_outreach_drafts",
    "einvoice_records",
    "workflow_audit_log",
    "audit_log",
    "email_ingestion_receipts",
    "email_sync_state",
    "telegram_update_receipts",
    "integration_status",
    "token_vault",
    "protected_token_registry",
    "tokenized_content",
    "vault_rotation_jobs",
    "vault_key_versions",
)

EINVOICE_SEED_RECORDS = [
    dict(
        supplier_name="Tenaga Nasional Berhad", supplier_tin="C1234567890",
        buyer_name="FINBRAIN Sdn Bhd", invoice_no="TNB-2026-88213",
        issue_date=date(2026, 8, 10), currency="MYR", tax_type="SST", tax_rate="6%",
        total_amount="1240.00", status="validated",
    ),
    dict(
        supplier_name="Grab Malaysia", supplier_tin="C9988776655",
        buyer_name="FINBRAIN Sdn Bhd", invoice_no="GRB-4471209",
        issue_date=date(2026, 8, 9), currency="MYR", tax_type="SST", tax_rate="0%",
        total_amount="86.40", status="submitted",
    ),
    dict(
        supplier_name="Petronas Dagangan", supplier_tin="C1122334455",
        buyer_name="FINBRAIN Sdn Bhd", invoice_no="PDB-990214",
        issue_date=date(2026, 8, 8), currency="MYR", tax_type="SST", tax_rate="6%",
        total_amount="320.00", status="pending",
    ),
    dict(
        supplier_name="Office Supplies Sdn Bhd", supplier_tin=None,
        buyer_name="FINBRAIN Sdn Bhd", invoice_no="OS-4471",
        issue_date=date(2026, 8, 7), currency="MYR", tax_type="SST", tax_rate="6%",
        total_amount="545.90", status="review",
    ),
    dict(
        supplier_name="Astro Malaysia", supplier_tin="C5566778899",
        buyer_name="FINBRAIN Sdn Bhd", invoice_no="AST-118820",
        issue_date=date(2026, 8, 5), currency="MYR", tax_type="SST", tax_rate="6%",
        total_amount="129.00", status="validated",
    ),
    dict(
        supplier_name="Acme Retail", supplier_tin="C3344556677",
        buyer_name="FINBRAIN Sdn Bhd", invoice_no="ACM-77102",
        issue_date=date(2026, 8, 4), currency="MYR", tax_type="SST", tax_rate="6%",
        total_amount="980.00", status="submitted",
    ),
    dict(
        supplier_name="ACME RETAIL SDN BHD", supplier_tin="C3344556677",
        buyer_name="FINBRAIN Sdn Bhd", invoice_no="ACM-77145",
        issue_date=date(2026, 8, 2), currency="MYR", tax_type="SST", tax_rate="6%",
        total_amount="410.00", status="submitted",
    ),
    # --- Deliberate single-flaw test cases below, each isolating one readiness check ---
    dict(
        # Flaw: missing supplier TIN only -> critical (blocks submission).
        supplier_name="Kedai Runcit Maju", supplier_tin=None,
        buyer_name="FINBRAIN Sdn Bhd", invoice_no="KRM-3021",
        issue_date=date(2026, 8, 11), currency="MYR", tax_type="SST", tax_rate="6%",
        total_amount="212.50", status="review",
    ),
    dict(
        # Flaw: missing buyer name only -> warning.
        supplier_name="Segar Fresh Mart", supplier_tin="C4455667788",
        buyer_name=None, invoice_no="SFM-9012",
        issue_date=date(2026, 8, 12), currency="MYR", tax_type="SST", tax_rate="6%",
        total_amount="88.20", status="submitted",
    ),
    dict(
        # Flaw: missing tax type only -> warning.
        supplier_name="Bina Jaya Hardware", supplier_tin="C6677889900",
        buyer_name="FINBRAIN Sdn Bhd", invoice_no="BJH-5510",
        issue_date=date(2026, 8, 13), currency="MYR", tax_type=None, tax_rate=None,
        total_amount="1560.00", status="submitted",
    ),
    dict(
        # Flaw: name variant, spelling 1 of 3 -> warning (all three should flag).
        supplier_name="Impian Services", supplier_tin="C7788990011",
        buyer_name="FINBRAIN Sdn Bhd", invoice_no="IMP-1001",
        issue_date=date(2026, 8, 14), currency="MYR", tax_type="SST", tax_rate="6%",
        total_amount="640.00", status="submitted",
    ),
    dict(
        # Flaw: name variant, spelling 2 of 3.
        supplier_name="IMPIAN SERVICES SDN BHD", supplier_tin="C7788990011",
        buyer_name="FINBRAIN Sdn Bhd", invoice_no="IMP-1014",
        issue_date=date(2026, 8, 15), currency="MYR", tax_type="SST", tax_rate="6%",
        total_amount="720.00", status="submitted",
    ),
    dict(
        # Flaw: name variant, spelling 3 of 3.
        supplier_name="Impian Services Sdn. Bhd.", supplier_tin="C7788990011",
        buyer_name="FINBRAIN Sdn Bhd", invoice_no="IMP-1029",
        issue_date=date(2026, 8, 16), currency="MYR", tax_type="SST", tax_rate="6%",
        total_amount="305.00", status="submitted",
    ),
    dict(
        # Flaw: combined (missing TIN AND missing buyer name) -> still critical, not double-counted.
        supplier_name="Damaged Goods Trading", supplier_tin=None,
        buyer_name=None, invoice_no="DGT-4400",
        issue_date=date(2026, 8, 17), currency="MYR", tax_type=None, tax_rate=None,
        total_amount="95.00", status="review",
    ),
    dict(
        # No flaws -> passing.
        supplier_name="Bright Solutions Sdn Bhd", supplier_tin="C8899001122",
        buyer_name="FINBRAIN Sdn Bhd", invoice_no="BSS-7701",
        issue_date=date(2026, 8, 18), currency="MYR", tax_type="SST", tax_rate="6%",
        total_amount="1980.00", status="validated",
    ),
]


def _generate_seed_uin() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "MY29A" + "".join(secrets.choice(alphabet) for _ in range(6))


def seed_einvoice_records(db) -> None:
    """Seed EInvoiceRecord rows directly — no ingestion/LLM pipeline needed."""
    from sqlalchemy import select
    from app.services import storage
    from app.services.einvoice_pdf import render_einvoice_pdf

    if db.scalar(select(EInvoiceRecord.id).limit(1)) is not None:
        return
    bucket = get_settings().einvoice_document_bucket
    try:
        storage.ensure_bucket(bucket)
    except Exception:
        pass
    for fields in EINVOICE_SEED_RECORDS:
        record_data = dict(fields)
        if record_data.get("status") == "validated" and not record_data.get("uin"):
            record_data["uin"] = _generate_seed_uin()
        record = EInvoiceRecord(**record_data)
        db.add(record)
        db.flush()
        try:
            pdf_bytes = render_einvoice_pdf(record)
            path = f"{record.id}.pdf"
            storage.upload_bytes(bucket, path, pdf_bytes, content_type="application/pdf")
            record.document_storage_path = path
        except Exception:
            pass
    db.commit()
    print(f"seeded {len(EINVOICE_SEED_RECORDS)} einvoice_records")


def adapt_seed_record(record: dict) -> CanonicalIngestionRecord:
    """Convert a demo fixture into the canonical connector-neutral contract."""
    return CanonicalIngestionRecord(
        source_record_id=record["source_record_id"],
        source_system=record["source_system"],
        record_type=record["record_type"],
        text=record["text"],
        occurred_at=datetime.fromisoformat(record["occurred_at"]),
        metadata={"dataset": "track2_demo", **record.get("metadata", {})},
    )


def reset_demo_data() -> None:
    """Clear only FinBrain application rows while preserving schema, migrations, and RLS."""
    settings = get_settings()
    with SessionLocal() as db:
        if settings.database_backend == "postgresql":
            qualified = ", ".join(f"public.{table}" for table in RESET_TABLES)
            db.execute(text(f"truncate table {qualified} restart identity"))
        else:
            for table in RESET_TABLES:
                db.execute(text(f"delete from {table}"))
        db.commit()


def run(
    *,
    refresh: bool = False,
    reset: bool = False,
    excluded_sources: set[str] | None = None,
) -> None:
    initialize_local_schema()
    if reset:
        reset_demo_data()
        print("cleared FinBrain application data; schema and migrations preserved")
    excluded = excluded_sources or set()
    with SessionLocal() as db:
        for record in SAMPLE_RECORDS:
            if record["source_system"] in excluded:
                continue
            canonical = adapt_seed_record(record)
            result = ingest_canonical_record(db, canonical, refresh=refresh)
            print(
                f"seeded {canonical.source_system}/{result.source_record_id} "
                f"[{result.processing_status}] via {result.enrichment_mode or 'none'}"
            )
        seed_einvoice_records(db)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed FinBrain through the protected pipeline.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Retokenize and re-embed existing seed records without deleting audit history.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all FinBrain application rows before inserting the clean demo dataset.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Required confirmation for --reset.",
    )
    parser.add_argument(
        "--exclude-source",
        action="append",
        default=[],
        choices=sorted({record["source_system"] for record in SAMPLE_RECORDS}),
        help=(
            "Omit a seeded source system; repeat for more than one. "
            "Useful when a live connector supplies that source."
        ),
    )
    args = parser.parse_args()
    if args.reset and not args.yes:
        parser.error("--reset requires --yes because it deletes existing FinBrain application data")
    run(
        refresh=args.refresh,
        reset=args.reset,
        excluded_sources=set(args.exclude_source),
    )
