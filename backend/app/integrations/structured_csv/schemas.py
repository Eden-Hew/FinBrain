from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.schemas import IngestionResult

SCHEMA_NAME = "invoice_register_v1"


@dataclass(frozen=True, slots=True)
class CsvValidationIssue:
    code: str
    row_number: int | None = None
    field: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedInvoiceRow:
    row_number: int
    invoice_id: str
    customer: str
    amount: Decimal
    status: str
    assigned_owner: str
    due_date: date


@dataclass(frozen=True, slots=True)
class ParsedStructuredCsv:
    total_rows: int
    rows: list[ParsedInvoiceRow] = field(default_factory=list)
    issues: list[CsvValidationIssue] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class StructuredCsvRowResult:
    row_number: int
    source_record_id: str
    ingestion: IngestionResult


@dataclass(frozen=True, slots=True)
class StructuredCsvBatchResult:
    batch_ref: str
    schema_name: str
    status: str
    total_rows: int
    valid_rows: int
    failed_rows: int
    protected_rows: int
    ready_rows: int
    rows: list[StructuredCsvRowResult] = field(default_factory=list)
    issues: list[CsvValidationIssue] = field(default_factory=list)
