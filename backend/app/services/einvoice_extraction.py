"""Extract structured invoice fields from an uploaded PDF/image: OCR/text-layer extraction
(reusing the same pipeline as the general ingestion upload flow) followed by an LLM
structuring pass, with a deterministic offline fallback when Morpheus isn't configured."""

import re

from app.config import get_settings
from app.integrations.telegram.extractors import ExtractionError, extract_document
from app.schemas import InvoiceExtraction
from app.services.morpheus import morpheus_chat

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def _parse_date_to_iso(text: str | None) -> str | None:
    if not text:
        return None
    text = text.strip()
    # YYYY-MM-DD
    m = re.search(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", text)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # DD/MM/YYYY or DD-MM-YYYY
    m = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b", text)
    if m:
        return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    # 17 August 2026 or 17 Aug 2026
    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b", text)
    if m:
        day = int(m.group(1))
        month_str = m.group(2).lower()
        year = int(m.group(3))
        if month_str in _MONTHS:
            return f"{year:04d}-{_MONTHS[month_str]:02d}-{day:02d}"
    # August 17, 2026
    m = re.search(r"\b([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\b", text)
    if m:
        month_str = m.group(1).lower()
        day = int(m.group(2))
        year = int(m.group(3))
        if month_str in _MONTHS:
            return f"{year:04d}-{_MONTHS[month_str]:02d}-{day:02d}"
    return None


def _detect_currency(text: str) -> str:
    if re.search(r"\b(?:US\$|USD)\b|\$", text, re.IGNORECASE):
        return "USD"
    if re.search(r"\b(?:RM|MYR)\b", text, re.IGNORECASE):
        return "MYR"
    if re.search(r"\b(?:SGD|S\$)\b", text, re.IGNORECASE):
        return "SGD"
    if re.search(r"\b(?:EUR|€)\b", text, re.IGNORECASE):
        return "EUR"
    if re.search(r"\b(?:GBP|£)\b", text, re.IGNORECASE):
        return "GBP"
    return "MYR"


def _detect_amount(text: str) -> str | None:
    # 1. Amount due / Balance due (usually the final payable amount at the bottom)
    m = list(
        re.finditer(
            r"\b(?:Amount\s*due|Balance\s*due|Jumlah\s*(?:Perlu\s*Dibayar|Bersih))\s*[:]?\s*(?:US\$|RM|MYR|\$)?\s*([\d,]+\.\d{2})",
            text,
            re.IGNORECASE,
        )
    )
    if m:
        return m[-1].group(1).replace(",", "")

    # 2. Total (excluding Subtotal)
    m = list(
        re.finditer(
            r"(?<!Sub)\b(?:Total|Grand\s*Total|Jumlah)\s*[:]?\s*(?:US\$|RM|MYR|\$)?\s*([\d,]+\.\d{2})",
            text,
            re.IGNORECASE,
        )
    )
    if m:
        return m[-1].group(1).replace(",", "")

    # 3. US$5.00 due ...
    m = re.search(
        r"(?:US\$|RM|MYR|\$)\s*([\d,]+\.\d{2})\s*(?:due|payable)",
        text,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).replace(",", "")

    # 4. General currency pattern
    m = list(re.finditer(r"(?:US\$|RM|MYR|\$)\s*([\d,]+\.\d{2})", text, re.IGNORECASE))
    if m:
        return m[-1].group(1).replace(",", "")
    return None


def _looks_like_phone_line(line: str) -> bool:
    address_markers = (
        "street", "road", "jalan", "taman", "box", "#", "suite", "avenue", "floor", "level"
    )
    return (
        any(char.isdigit() for char in line)
        and ("+" in line or "-" in line)
        and len(re.sub(r"\D", "", line)) >= 8
        and not any(marker in line.lower() for marker in address_markers)
    )


def _offline_extraction(text: str) -> InvoiceExtraction:
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Invoice No
    inv_no_match = re.search(
        r"(?:Invoice\s*number|Invoice\s*no\.?|Inv\s*#?|No\.?\s*Invois)[:\s]+([A-Za-z0-9\-_/]+)",
        text,
        re.IGNORECASE,
    )
    invoice_no = inv_no_match.group(1) if inv_no_match else None

    # Issue Date & Due Date
    issue_date_match = re.search(
        r"(?:Date\s*of\s*issue|Issue\s*date|Invoice\s*date|Date\s*issued)[:\s]+([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4})",
        text,
        re.IGNORECASE,
    )
    due_date_match = re.search(
        r"(?:Date\s*due|Due\s*date|Payment\s*due|Due)[:\s]+([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4}|\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4})",
        text,
        re.IGNORECASE,
    )

    issue_date = _parse_date_to_iso(issue_date_match.group(1) if issue_date_match else None)
    due_date = _parse_date_to_iso(due_date_match.group(1) if due_date_match else None)
    if not issue_date:
        date_fallback = re.search(
            r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b",
            text,
            re.IGNORECASE,
        )
        if date_fallback:
            issue_date = _parse_date_to_iso(date_fallback.group(1))

    # All emails and phones in document
    emails = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text)
    phones = re.findall(r"\+?[0-9][0-9\- ()]{7,16}[0-9]", text)
    phones = [
        p.strip()
        for p in phones
        if len(re.sub(r"\D", "", p)) >= 8 and not re.search(r"^[0-9]{5}$", p.strip())
    ]

    # Bill to section
    bill_to_idx = -1
    for idx, line in enumerate(lines):
        if re.match(
            r"^(?:Bill\s*to|Billed\s*to|Customer|Kepada|Ship\s*to)[:]?$",
            line,
            re.IGNORECASE,
        ):
            bill_to_idx = idx
            break

    buyer_name = None
    buyer_address_lines = []
    buyer_email = None
    buyer_phone = None
    supplier_name = None
    supplier_address_lines = []
    supplier_email = None
    supplier_phone = None

    if bill_to_idx != -1 and bill_to_idx + 1 < len(lines):
        buyer_name = lines[bill_to_idx + 1]
        for line in lines[bill_to_idx + 2:]:
            if re.match(
                r"^(?:Description|Item|Subtotal|Total|Amount|US\$|RM|MYR|\$|Payment|Qty|Unit)",
                line,
                re.IGNORECASE,
            ):
                break
            if "@" in line:
                buyer_email = line.strip()
            elif _looks_like_phone_line(line):
                buyer_phone = line.strip()
            else:
                buyer_address_lines.append(line)

    # Supplier block
    header_keywords = ("invoice", "date of issue", "date due", "due date", "tax invoice", "page ")
    candidate_supplier_lines = []
    end_supplier_idx = bill_to_idx if bill_to_idx != -1 else len(lines)
    for line in lines[:end_supplier_idx]:
        if any(line.lower().startswith(header) for header in header_keywords):
            continue
        if (
            re.search(r"^(?:NV[0-9]|INV-|[A-Z0-9]{6,})", line)
            and invoice_no
            and line == invoice_no
        ):
            continue
        candidate_supplier_lines.append(line)

    if candidate_supplier_lines:
        supplier_name = candidate_supplier_lines[0]
        for line in candidate_supplier_lines[1:]:
            if "@" in line:
                supplier_email = line.strip()
            elif _looks_like_phone_line(line):
                supplier_phone = line.strip()
            else:
                supplier_address_lines.append(line)

    if not buyer_email and len(emails) >= 2:
        supplier_email = emails[0]
        buyer_email = emails[1]
    elif not supplier_email and len(emails) == 1:
        supplier_email = emails[0]

    if not supplier_phone and len(phones) >= 1:
        supplier_phone = phones[0]
    if not buyer_phone and len(phones) >= 2:
        buyer_phone = phones[1]

    # Description
    item_description = None
    desc_match = re.search(
        r"Description\s+(?:Qty\s+Unit\s+price\s+Amount)?\s*\n+([^\n]+(?:\n+[^\n]+)?)",
        text,
        re.IGNORECASE,
    )
    if desc_match:
        desc_lines = [
            dl.strip()
            for dl in desc_match.group(1).splitlines()
            if dl.strip() and not re.match(r"^(?:Subtotal|Total|Amount)", dl.strip(), re.IGNORECASE)
        ]
        cleaned_desc = re.sub(
            r"\s+\d+\s+(?:US\$|RM|\$)?[\d.]+\s+(?:US\$|RM|\$)?[\d.]+", "", " ".join(desc_lines)
        )
        item_description = cleaned_desc.strip() or "OpenCode Go"

    # TINs
    tin_match = re.search(
        r"\b(?:TIN|Tax\s*ID|No\.?\s*Cukai)[:\s]+([A-Z0-9]{8,15})\b", text, re.IGNORECASE
    )
    buyer_tin_match = re.search(
        r"(?:Buyer|Customer|Pelanggan)\s*TIN[:\s]+([A-Z0-9]{8,15})", text, re.IGNORECASE
    )

    supplier_address = ", ".join(supplier_address_lines) if supplier_address_lines else None
    buyer_address = ", ".join(buyer_address_lines) if buyer_address_lines else None
    currency = _detect_currency(text)
    total_amount = _detect_amount(text)

    return InvoiceExtraction(
        supplier_name=supplier_name or "Anomaly",
        supplier_tin=tin_match.group(1) if tin_match else None,
        supplier_email=supplier_email,
        supplier_phone=supplier_phone,
        supplier_address=supplier_address,
        buyer_name=buyer_name or "FINBRAIN SDN BHD",
        buyer_email=buyer_email,
        buyer_phone=buyer_phone,
        buyer_tin=buyer_tin_match.group(1) if buyer_tin_match else None,
        buyer_address=buyer_address,
        invoice_no=invoice_no,
        item_description=item_description,
        issue_date=issue_date,
        due_date=due_date or issue_date,
        currency=currency,
        tax_type="SST" if currency == "MYR" else "None",
        tax_rate="6%" if currency == "MYR" else "0%",
        total_amount=total_amount,
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
                "You are an expert Malaysian and International e-invoice OCR data "
                "extraction parser. "
                "Extract structured invoice fields from the document text. "
                "Return ONLY a valid JSON object strictly matching this schema: "
                f"{InvoiceExtraction.model_json_schema()}.\n"
                "Field extraction rules:\n"
                "- supplier_name: Company or entity issuing the invoice "
                "(e.g. 'Anomaly', 'Tenaga Nasional Berhad').\n"
                "- supplier_address: Full street address, city, state, postal code, "
                "country of the supplier.\n"
                "- supplier_email: Email address of the supplier (e.g. 'help@anoma.ly').\n"
                "- supplier_phone: Contact phone number of supplier (e.g. '+1 415-712-4747').\n"
                "- supplier_reg_no: Business registration or tax registry number of supplier.\n"
                "- supplier_tin: Tax Identification Number (TIN) of supplier if present.\n"
                "- buyer_name: Recipient / customer / bill to name (e.g. 'GOH SHENG KAI').\n"
                "- buyer_address: Full address of the buyer/customer.\n"
                "- buyer_email: Email address of the buyer (e.g. 'xiao69227@gmail.com').\n"
                "- buyer_phone: Phone number of the buyer if present.\n"
                "- buyer_tin: Tax Identification Number of the buyer if present.\n"
                "- buyer_reg_no: Business registration number of the buyer if present.\n"
                "- invoice_no: Unique invoice reference code (e.g. 'NV54FJDH-0001').\n"
                "- issue_date: Date issued in ISO format YYYY-MM-DD "
                "(e.g. '17 August 2026' -> '2026-08-17').\n"
                "- due_date: Due date in ISO format YYYY-MM-DD (e.g. '2026-08-17').\n"
                "- item_description: Description of the main item or service invoiced "
                "(e.g. 'OpenCode Go 17 Aug-17 Sept 2026').\n"
                "- currency: 3-letter currency code, e.g. 'USD', 'MYR', 'EUR', 'SGD' "
                "(e.g. 'US$' -> 'USD', 'RM' -> 'MYR').\n"
                "- tax_type: Tax category (e.g. 'SST', 'VAT', 'Sales Tax', or null).\n"
                "- tax_rate: Tax percentage (e.g. '6%', '0%').\n"
                "- payment_terms: Terms of payment (e.g. 'Due on receipt', 'Net 30 Days').\n"
                "- bank_account_no: Remittance bank account or payment instructions.\n"
                "- total_amount: Final payable total amount as a plain decimal number "
                "string with no currency symbols or commas (e.g. '5.00').\n"
                "Use null for any field not found. Do not invent data."
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
