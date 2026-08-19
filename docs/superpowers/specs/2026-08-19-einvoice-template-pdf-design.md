# Malaysia LHDN/MyInvois e-Invoice PDF Template Design Specification

**Date:** 2026-08-19  
**Status:** Approved  
**Target:** Python ReportLab Single-Page PDF Generator for Malaysia e-Invoice Compliance  

---

## 1. Overview & Purpose
This document specifies the technical design for rendering LHDN/MyInvois-compliant Malaysia e-Invoices as a single-page printable PDF document. The template strictly satisfies the visual guidelines, style tokens, and data schema specified for MyInvois v4.6 compliance while retaining backwards compatibility with the FinBrain `EInvoiceRecord` data model.

---

## 2. Style Tokens & Visual System

| Token | Value | Applied To |
|---|---|---|
| **Navy** | `#1F3B57` | Main title, table headers, section banner headers, total payable row |
| **Navy Dark** | `#16283A` | IRBM validation strip background |
| **Gold Accent** | `#C9A227` | Decorative divider bar below header, status highlight |
| **Light Grey** | `#F2F4F6` | Table alternating zebra-stripes, subtle container backgrounds |
| **Mid Grey** | `#6B7280` | Field labels (UPPERCASE, ~6.5–7pt) |
| **Border Grey** | `#D9DCE1` | Box outlines, cell borders, subtle separating rules |
| **Near Black** | `#1A202C` | Primary text and field values (~8.5–10pt) |
| **White** | `#FFFFFF` | Text on navy headers and dark validation strip |
| **Font Family** | Helvetica / Helvetica-Bold (Standard ReportLab equivalent for Calibri), Courier / Courier-Bold (for Consolas IRBM UIN) |

---

## 3. Document Structure (Top to Bottom)

The PDF is generated on an **A4 page (210mm x 297mm)** with 12mm page margins.

1. **Header Band:**
   - **Left Column:** Supplier Name (14pt Bold Navy `#1F3B57`), Registration No., Address lines, Contact Phone and Email.
   - **Right Column:** Right-aligned title `"e-INVOICE"` (18pt Bold Navy), Invoice Code / Number, Issue Date, Issue Time, Invoice Type (e.g. `Invoice`, `Credit Note`, `Debit Note`, `Refund Note`, `Self-Billed`), Currency Code (e.g. `MYR`), and Exchange Rate (if foreign currency).
2. **Gold Accent Divider Line:**
   - 2pt solid horizontal line colored Gold `#C9A227`.
3. **IRBM Validation Strip:**
   - Dark Navy (`#16283A`) container spanning full printable width.
   - **Left side:** Monospace Consolas/Courier-Bold Unique Identifier Number (`irbm_unique_id`), Validation Timestamp, and Validation Status (`VALIDATED` / `SUBMITTED`).
   - **Right side:** QR Code placeholder box with target brackets and label.
4. **Parties Section (Side-by-Side 2-Box Grid):**
   - **Box 1: SUPPLIER (BILL FROM)**:
     - Header: Navy banner with white text.
     - Fields: Name, TIN, Registration No., SST Registration No., Tourism Tax No., MSIC Code & Business Activity, Address, Contact.
   - **Box 2: BUYER (BILL TO)**:
     - Header: Navy banner with white text.
     - Fields: Name, TIN, Registration No., SST Registration No., Address, Contact, Shipping Recipient (Name/Address/TIN if present).
   - Label & Value format: 6.5pt UPPERCASE Mid Grey label directly above 8.5pt Near Black value.
5. **Itemised Details Table:**
   - Header Row: Navy `#1F3B57` background with white text.
   - Columns:
     1. `#` (Item index)
     2. `Description & Classification` (Classification code + Item description)
     3. `Qty`
     4. `Unit Price (MYR)`
     5. `Disc.` (Discount rate/amount)
     6. `Tax` (Tax type, rate & exemption if applicable)
     7. `Subtotal (MYR)`
   - Zebra-striped alternating rows (`#FFFFFF` and `#F2F4F6`), subtle horizontal gridlines (`#D9DCE1`).
6. **Totals Block:**
   - Right-aligned stacked summary table:
     - Subtotal
     - Total Discount
     - Total Excluding Tax
     - Total Tax (SST / Tax amount)
     - Total Including Tax
     - **TOTAL PAYABLE** (Highlighted Navy bar, white 11pt bold text).
7. **Payment Information:**
   - 2-column key-value grid: Payment Mode, Bank Account No., Terms, Due Date, Payment Reference No., Bill Reference No.
8. **Footer:**
   - Disclaimer: *"This document is a human-readable printable representation of an IRBM MyInvois-validated e-Invoice."*
   - Generation timestamp and FinBrain OS identifier.

---

## 4. Data Models & Normalization

The service accepts either full nested dictionaries matching the LHDN schema or flat `EInvoiceRecord` instances/keyword arguments.

### Canonical Data Schema:
```python
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

@dataclass
class DocumentInfo:
    einvoice_version: str = "1.1"
    einvoice_type: str = "Invoice"
    einvoice_code: str = "INV-0000"
    original_einvoice_ref: Optional[str] = None
    issue_date: str = ""
    issue_time: str = "00:00:00"
    irbm_unique_id: Optional[str] = None
    validation_datetime: Optional[str] = None
    currency_code: str = "MYR"
    exchange_rate: Optional[Decimal] = None

@dataclass
class SupplierInfo:
    name: str = ""
    tin: str = ""
    registration_no: str = ""
    sst_registration_no: Optional[str] = None
    tourism_tax_no: Optional[str] = None
    address: str = ""
    contact: str = ""
    email: str = ""
    msic_code: str = ""
    business_activity: str = ""

@dataclass
class BuyerInfo:
    name: str = ""
    tin: str = ""
    registration_no: str = ""
    sst_registration_no: Optional[str] = None
    address: str = ""
    contact: str = ""
    email: str = ""

@dataclass
class ShippingInfo:
    name: Optional[str] = None
    address: Optional[str] = None
    tin: Optional[str] = None
    registration_no: Optional[str] = None

@dataclass
class LineItemInfo:
    description: str = ""
    classification_code: str = "001"
    quantity: Decimal = Decimal("1")
    unit_of_measure: Optional[str] = "unit"
    unit_price: Decimal = Decimal("0.00")
    discount_rate: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    tax_type: str = "SST"
    tax_rate: Decimal = Decimal("6.0")
    tax_amount: Decimal = Decimal("0.00")
    tax_exemption_details: Optional[str] = None
    amount_exempted: Optional[Decimal] = None
    line_subtotal: Decimal = Decimal("0.00")

@dataclass
class TotalsInfo:
    subtotal: Decimal = Decimal("0.00")
    total_discount: Decimal = Decimal("0.00")
    total_excluding_tax: Decimal = Decimal("0.00")
    total_tax: Decimal = Decimal("0.00")
    total_including_tax: Decimal = Decimal("0.00")
    total_payable: Decimal = Decimal("0.00")

@dataclass
class PaymentInfo:
    mode: Optional[str] = "Bank Transfer"
    bank_account_no: Optional[str] = None
    terms: Optional[str] = "Net 30 Days"
    due_date: Optional[str] = None
    payment_reference_no: Optional[str] = None
    bill_reference_no: Optional[str] = None

@dataclass
class EInvoicePdfData:
    document: DocumentInfo
    supplier: SupplierInfo
    buyer: BuyerInfo
    shipping_recipient: Optional[ShippingInfo]
    line_items: list[LineItemInfo]
    totals: TotalsInfo
    payment: PaymentInfo
```

### Normalizer Behavior:
- When given an `EInvoiceRecord` database instance or legacy kwargs (`supplier_name`, `supplier_tin`, `buyer_name`, `invoice_no`, `issue_date`, `currency`, `tax_type`, `tax_rate`, `total_amount`, `status`, `uin`):
  - Automatically synthesizes realistic default registration numbers, addresses, and line-item breakdowns.
  - Correctly computes tax amounts and subtotal according to `tax_rate` and `total_amount`.
  - Sets IRBM validation status and UIN from record fields.

---

## 5. Implementation Architecture

1. **`backend/app/services/einvoice_pdf.py`**:
   - Primary service module containing schema dataclasses, normalizer logic, color tokens, and ReportLab canvas/table rendering logic.
   - Public entry point: `render_einvoice_pdf(data_or_record, ...) -> bytes`.
2. **`backend/seed/generate_einvoice_pdf.py`**:
   - Re-exports `render_einvoice_pdf` to ensure backwards compatibility with any existing scripts or tests.
3. **`backend/tests/test_einvoice_pdf.py`**:
   - Unit tests covering full payload rendering, legacy kwargs rendering, missing optional fields, and byte validity.

---

## 6. Verification & Quality Gates
1. Run `pytest backend/tests/test_einvoice_pdf.py` to test all rendering branches.
2. Run full pytest suite across backend (`pytest`) to guarantee zero regressions.
3. Verify single-page fit constraint and visual hierarchy against the specification.
