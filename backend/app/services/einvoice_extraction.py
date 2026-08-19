"""Extract structured invoice fields from an uploaded PDF: OCR/text-layer extraction
(reusing the same pipeline as the general ingestion upload flow) followed by an LLM
structuring pass, with a deterministic offline fallback when Morpheus isn't configured."""
import re

from app.config import get_settings
from app.integrations.telegram.extractors import ExtractionError, extract_document
from app.schemas import InvoiceExtraction
from app.services.morpheus import morpheus_chat

_AMOUNT_PATTERN = re.compile(r"(?:RM|MYR)\s*([\d,]+\.\d{2})", re.IGNORECASE)
_TIN_PATTERN = re.compile(r"\bTIN[:\s]+([A-Z0-9]{8,15})\b", re.IGNORECASE)
_INVOICE_NO_PATTERN = re.compile(
    r"Invoice\s*(?:No\.?|Number)?[:\s]+([A-Za-z0-9\-/]+)", re.IGNORECASE
)
_DATE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _offline_extraction(text: str) -> InvoiceExtraction:
    amount_match = _AMOUNT_PATTERN.search(text)
    tin_match = _TIN_PATTERN.search(text)
    invoice_no_match = _INVOICE_NO_PATTERN.search(text)
    date_match = _DATE_PATTERN.search(text)
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), None)
    return InvoiceExtraction(
        supplier_name=first_line,
        supplier_tin=tin_match.group(1) if tin_match else None,
        invoice_no=invoice_no_match.group(1) if invoice_no_match else None,
        issue_date=date_match.group(1) if date_match else None,
        currency="MYR",
        total_amount=amount_match.group(1).replace(",", "") if amount_match else None,
    )


def extract_invoice_fields(data: bytes, *, filename: str, mime_type: str) -> InvoiceExtraction:
    try:
        extracted = extract_document(data, filename=filename, mime_type=mime_type)
    except ExtractionError as error:
        raise ValueError(str(error)) from error

    settings = get_settings()
    if settings.morpheus_api_key:
        try:
            instruction = (
                "Extract invoice fields from the document text below. Return only JSON "
                f"matching this schema: {InvoiceExtraction.model_json_schema()}. Use null "
                "for any field you cannot find with confidence — never guess. issue_date "
                "must be ISO format YYYY-MM-DD if present. total_amount must be a plain "
                "decimal number as a string with no currency symbols, commas, or spaces."
            )
            response = morpheus_chat([
                {"role": "system", "content": instruction},
                {"role": "user", "content": extracted.text[:8000]},
            ])
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.strip())
            return InvoiceExtraction.model_validate_json(cleaned)
        except Exception:
            if not settings.allow_offline_demo:
                raise

    if not settings.allow_offline_demo:
        raise RuntimeError("Morpheus is required for invoice extraction")
    return _offline_extraction(extracted.text)
