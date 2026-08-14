import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from app.config import Settings, get_settings
from app.integrations.structured_csv.schemas import (
    CsvValidationIssue,
    ParsedInvoiceRow,
    ParsedStructuredCsv,
)

HEADER_ALIASES = {
    "invoice_id": "invoice_id",
    "invoice": "invoice_id",
    "customer": "customer",
    "customer_name": "customer",
    "amount": "amount",
    "amount_myr": "amount",
    "status": "status",
    "assigned_owner": "assigned_owner",
    "owner": "assigned_owner",
    "due_date": "due_date",
    "due": "due_date",
}
REQUIRED_HEADERS = {
    "invoice_id",
    "customer",
    "amount",
    "status",
    "assigned_owner",
    "due_date",
}
STATUS_ALIASES = {
    "pending approval": "pending_approval",
    "pending_approval": "pending_approval",
    "overdue": "overdue",
    "paid": "paid",
    "refund requested": "refund_requested",
    "refund_requested": "refund_requested",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "unknown": "unknown",
}
INVOICE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
AMOUNT_PATTERN = re.compile(r"^(?:RM\s*)?\d{1,12}(?:,\d{3})*(?:\.\d{1,2})?$", re.IGNORECASE)


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("windows-1252")


def _normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().casefold()).strip("_")


def _issue(code: str, row: int | None = None, field: str | None = None):
    return CsvValidationIssue(code=code, row_number=row, field=field)


def parse_invoice_csv(data: bytes, *, settings: Settings | None = None) -> ParsedStructuredCsv:
    limits = settings or get_settings()
    if len(data) > limits.structured_csv_max_file_bytes:
        return ParsedStructuredCsv(0, issues=[_issue("file_too_large")])
    if b"\x00" in data:
        return ParsedStructuredCsv(0, issues=[_issue("nul_byte")])

    try:
        text = _decode(data).replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError:
        return ParsedStructuredCsv(0, issues=[_issue("unsupported_encoding")])
    if not text.strip():
        return ParsedStructuredCsv(0, issues=[_issue("empty_file")])

    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    try:
        records = list(csv.reader(io.StringIO(text), dialect))
    except csv.Error:
        return ParsedStructuredCsv(0, issues=[_issue("malformed_csv")])
    if not records:
        return ParsedStructuredCsv(0, issues=[_issue("empty_file")])
    if len(records[0]) > limits.structured_csv_max_columns:
        return ParsedStructuredCsv(0, issues=[_issue("too_many_columns")])

    raw_headers = [_normalized_header(value) for value in records[0]]
    normalized_headers = [HEADER_ALIASES.get(value) for value in raw_headers]
    if any(value is None for value in normalized_headers):
        return ParsedStructuredCsv(0, issues=[_issue("unsupported_header")])
    headers = [value for value in normalized_headers if value is not None]
    if len(set(headers)) != len(headers):
        return ParsedStructuredCsv(0, issues=[_issue("duplicate_header")])
    if set(headers) != REQUIRED_HEADERS:
        return ParsedStructuredCsv(0, issues=[_issue("missing_required_header")])

    data_rows = records[1:]
    if len(data_rows) > limits.structured_csv_max_rows:
        return ParsedStructuredCsv(len(data_rows), issues=[_issue("too_many_rows")])

    parsed: list[ParsedInvoiceRow] = []
    issues: list[CsvValidationIssue] = []
    invoice_ids: set[str] = set()
    for row_number, values in enumerate(data_rows, start=2):
        if len(values) != len(headers):
            issues.append(_issue("column_count", row_number))
            continue
        fields = {header: value.strip() for header, value in zip(headers, values, strict=True)}
        overlong = next(
            (
                name
                for name, value in fields.items()
                if len(value) > limits.structured_csv_max_cell_chars
            ),
            None,
        )
        if overlong:
            issues.append(_issue("cell_too_long", row_number, overlong))
            continue

        row_issues: list[CsvValidationIssue] = []
        invoice_id = fields["invoice_id"]
        invoice_key = invoice_id.casefold()
        if not INVOICE_PATTERN.fullmatch(invoice_id):
            row_issues.append(_issue("invalid_invoice_id", row_number, "invoice_id"))
        elif invoice_key in invoice_ids:
            row_issues.append(_issue("duplicate_invoice_id", row_number, "invoice_id"))
        if not fields["customer"]:
            row_issues.append(_issue("missing_customer", row_number, "customer"))

        raw_amount = fields["amount"]
        try:
            if not AMOUNT_PATTERN.fullmatch(raw_amount):
                raise InvalidOperation
            amount = Decimal(re.sub(r"^(?i:RM)\s*", "", raw_amount).replace(",", ""))
            if amount < 0:
                raise InvalidOperation
        except InvalidOperation:
            amount = Decimal(0)
            row_issues.append(_issue("invalid_amount", row_number, "amount"))

        status = STATUS_ALIASES.get(fields["status"].casefold())
        if status is None:
            status = "unknown"
            row_issues.append(_issue("invalid_status", row_number, "status"))
        try:
            due_date = date.fromisoformat(fields["due_date"])
        except ValueError:
            due_date = date.min
            row_issues.append(_issue("invalid_due_date", row_number, "due_date"))

        if row_issues:
            issues.extend(row_issues)
            continue
        invoice_ids.add(invoice_key)
        parsed.append(
            ParsedInvoiceRow(
                row_number=row_number,
                invoice_id=invoice_id,
                customer=fields["customer"],
                amount=amount,
                status=status,
                assigned_owner=fields["assigned_owner"],
                due_date=due_date,
            )
        )
    return ParsedStructuredCsv(total_rows=len(data_rows), rows=parsed, issues=issues)
