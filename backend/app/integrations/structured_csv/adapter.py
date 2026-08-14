import hashlib
import hmac

from app.config import get_settings
from app.integrations.structured_csv.schemas import SCHEMA_NAME, ParsedInvoiceRow
from app.schemas import CanonicalIngestionRecord
from app.security.tokenize import amount_band_index


def _hmac_ref(purpose: str, value: bytes) -> str:
    payload = purpose.encode() + b"\x00" + value
    return hmac.new(get_settings().token_root_secret.encode(), payload, hashlib.sha256).hexdigest()


def batch_reference(data: bytes, schema_name: str = SCHEMA_NAME) -> str:
    return _hmac_ref("structured-csv-batch", schema_name.encode() + b"\x00" + data)


def row_reference(invoice_id: str, schema_name: str = SCHEMA_NAME) -> str:
    normalized = invoice_id.strip().casefold().encode()
    return _hmac_ref("structured-csv-row", schema_name.encode() + b"\x00" + normalized)


def adapt_invoice_row(
    row: ParsedInvoiceRow,
    *,
    batch_ref: str,
    origin_channel: str = "web_upload",
) -> CanonicalIngestionRecord:
    row_ref = row_reference(row.invoice_id)
    amount_text = format(row.amount, ".2f")
    owner = row.assigned_owner or "Unassigned"
    text = (
        f"Invoice ID: {row.invoice_id}\n"
        f"Customer: {row.customer}\n"
        f"Amount: RM {amount_text}\n"
        f"Status: {row.status.replace('_', ' ')}\n"
        f"Assigned owner: {owner}\n"
        f"Due date: {row.due_date.isoformat()}"
    )
    return CanonicalIngestionRecord(
        source_record_id=f"spreadsheet:invoice:{row_ref[:24]}",
        source_system="spreadsheet",
        record_type="invoice_row",
        text=text,
        metadata={
            "schema_name": SCHEMA_NAME,
            "batch_ref": batch_ref,
            "row_number": str(row.row_number),
            "status": row.status,
            "due_date": row.due_date.isoformat(),
            "has_assigned_owner": str(bool(row.assigned_owner)).lower(),
            "amount_band": str(amount_band_index(row.amount)),
            "origin_channel": origin_channel,
        },
    )
