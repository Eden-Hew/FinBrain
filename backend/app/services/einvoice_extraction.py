"""Extract structured invoice fields from an uploaded PDF: OCR/text-layer extraction
(reusing the same pipeline as the general ingestion upload flow) followed by an LLM
structuring pass, with a deterministic offline fallback when Morpheus isn't configured."""
import re

from app.config import get_settings
from app.integrations.telegram.extractors import ExtractionError, extract_document
from app.schemas import InvoiceExtraction
from app.services.morpheus import morpheus_chat

_AMOUNT_PATTERN = re.compile(r"(?:RM|MYR|Total|Jumlah)\s*[:]?\s*([\d,]+\.\d{2})", re.IGNORECASE)
_TIN_PATTERN = re.compile(r"\b(?:TIN|Tax\s*ID|No\.?\s*Cukai)[:\s]+([A-Z0-9]{8,15})\b", re.IGNORECASE)
_BUYER_TIN_PATTERN = re.compile(r"(?:Buyer|Customer|Pelanggan)\s*TIN[:\s]+([A-Z0-9]{8,15})", re.IGNORECASE)
_INVOICE_NO_PATTERN = re.compile(
    r"(?:Invoice|Inv|Bil|No\.?\s*Invois)\s*(?:No\.?|Number|#)?[:\s]+([A-Za-z0-9\-/]+)", re.IGNORECASE
)
_DATE_PATTERN = re.compile(r"(?:Date|Tarikh|Issue\s*Date)[:\s]+(\d{4}-\d{2}-\d{2})|\b(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)
_DUE_DATE_PATTERN = re.compile(r"(?:Due\s*Date|Payment\s*Due|Tarikh\s*Matang)[:\s]+(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
_PHONE_PATTERN = re.compile(r"\b(?:\+?60|0)[1-9][0-9\- ]{7,10}\b")
_BUYER_PATTERN = re.compile(r"(?:Bill\s*To|Customer|Buyer|Billed\s*To|Kepada)[:\s]+([A-Za-z0-9\s.,&()'-]+?)(?:\n|$)", re.IGNORECASE)


def _offline_extraction(text: str) -> InvoiceExtraction:
    amount_match = _AMOUNT_PATTERN.search(text)
    tin_match = _TIN_PATTERN.search(text)
    buyer_tin_match = _BUYER_TIN_PATTERN.search(text)
    invoice_no_match = _INVOICE_NO_PATTERN.search(text)
    date_match = _DATE_PATTERN.search(text)
    due_date_match = _DUE_DATE_PATTERN.search(text)
    email_match = _EMAIL_PATTERN.search(text)
    phone_match = _PHONE_PATTERN.search(text)
    buyer_match = _BUYER_PATTERN.search(text)

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), None)
    issue_date_val = None
    if date_match:
        issue_date_val = date_match.group(1) or date_match.group(2)

    return InvoiceExtraction(
        supplier_name=first_line,
        supplier_tin=tin_match.group(1) if tin_match else None,
        supplier_email=email_match.group(0) if email_match else None,
        supplier_phone=phone_match.group(0) if phone_match else None,
        buyer_name=buyer_match.group(1).strip() if buyer_match else "FINBRAIN SDN BHD",
        buyer_tin=buyer_tin_match.group(1) if buyer_tin_match else None,
        invoice_no=invoice_no_match.group(1) if invoice_no_match else None,
        issue_date=issue_date_val,
        due_date=due_date_match.group(1) if due_date_match else None,
        currency="MYR",
        tax_type="SST",
        tax_rate="6%",
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
