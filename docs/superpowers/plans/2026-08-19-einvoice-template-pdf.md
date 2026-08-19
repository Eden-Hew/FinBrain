# Malaysia LHDN/MyInvois e-Invoice PDF Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a comprehensive, LHDN/MyInvois v4.6 compliant Malaysia e-Invoice PDF generator with accurate visual layout, style tokens, IRBM validation strip, parties boxes, line-items table, totals highlight, payment grid, and dual-input normalization.

**Architecture:** A modular ReportLab service (`backend/app/services/einvoice_pdf.py`) that normalizes either full JSON schema payloads or database `EInvoiceRecord` rows into a clean typed dataclass, rendering a single-page A4 PDF using ReportLab Flowables, Tables, and vector drawing canvas.

**Tech Stack:** Python 3.11+, ReportLab (>=4.2, <5), Pytest.

## Global Constraints
- Document format: Single-page A4 PDF (210mm x 297mm) with 12mm margins.
- Style Tokens:
  - Navy: `#1F3B57` (Headers, section banners, totals highlight)
  - Navy Dark: `#16283A` (IRBM validation strip background)
  - Gold Accent: `#C9A227` (Divider line, validation accents)
  - Light Grey: `#F2F4F6` (Zebra-striped table rows)
  - Mid Grey: `#6B7280` (Field labels)
  - Border Grey: `#D9DCE1` (Table & box borders)
  - Near Black: `#1A202C` (Body text and values)
- Typography: Helvetica / Helvetica-Bold for body/labels, Courier / Courier-Bold for monospace IRBM ID.

---

### Task 1: Data Schema & Input Normalization for e-Invoice PDF

**Files:**
- Create: `backend/app/services/einvoice_pdf.py`
- Test: `backend/tests/test_einvoice_pdf.py`

**Interfaces:**
- Produces:
  - `DocumentInfo`, `SupplierInfo`, `BuyerInfo`, `ShippingInfo`, `LineItemInfo`, `TotalsInfo`, `PaymentInfo`, `EInvoicePdfData` dataclasses.
  - `normalize_einvoice_data(data_or_record: dict | object | None = None, **kwargs) -> EInvoicePdfData`

- [ ] **Step 1: Write the failing unit tests for schema normalization**

Create `backend/tests/test_einvoice_pdf.py`:
```python
from decimal import Decimal
from datetime import date
from app.services.einvoice_pdf import normalize_einvoice_data, EInvoicePdfData

def test_normalize_full_dict_schema():
    payload = {
        "document": {
            "einvoice_version": "1.1",
            "einvoice_type": "Invoice",
            "einvoice_code": "INV-2026-001",
            "original_einvoice_ref": None,
            "issue_date": "2026-08-19",
            "issue_time": "14:30:00",
            "irbm_unique_id": "MY29A123456",
            "validation_datetime": "2026-08-19T14:35:00Z",
            "currency_code": "MYR",
            "exchange_rate": None,
        },
        "supplier": {
            "name": "Tenaga Nasional Berhad",
            "tin": "C1234567890",
            "registration_no": "199001009999",
            "sst_registration_no": "W10-1808-32000018",
            "tourism_tax_no": None,
            "address": "No. 129, Jalan Bangsar, 59200 Kuala Lumpur",
            "contact": "+603-2296 5566",
            "email": "billing@tnb.com.my",
            "msic_code": "35101",
            "business_activity": "Electric power generation, transmission and distribution",
        },
        "buyer": {
            "name": "FINBRAIN SDN BHD",
            "tin": "C9876543210",
            "registration_no": "202401012345",
            "sst_registration_no": None,
            "address": "Level 20, Menara FinTech, 50450 Kuala Lumpur",
            "contact": "+603-2111 2222",
            "email": "finance@finbrain.os",
        },
        "shipping_recipient": None,
        "line_items": [
            {
                "description": "Commercial Electricity Tariff C1 (Peak/Off-Peak)",
                "classification_code": "001",
                "quantity": 1,
                "unit_of_measure": "kWh",
                "unit_price": 1169.81,
                "discount_rate": 0,
                "discount_amount": 0,
                "tax_type": "SST",
                "tax_rate": 6.0,
                "tax_amount": 70.19,
                "tax_exemption_details": None,
                "amount_exempted": None,
                "line_subtotal": 1240.00,
            }
        ],
        "totals": {
            "subtotal": 1169.81,
            "total_discount": 0.00,
            "total_excluding_tax": 1169.81,
            "total_tax": 70.19,
            "total_including_tax": 1240.00,
            "total_payable": 1240.00,
        },
        "payment": {
            "mode": "Bank Transfer",
            "bank_account_no": "Maybank 514011223344",
            "terms": "Net 30 Days",
            "due_date": "2026-09-18",
            "payment_reference_no": "PAY-88213",
            "bill_reference_no": "BIL-9910",
        },
    }
    normalized = normalize_einvoice_data(payload)
    assert isinstance(normalized, EInvoicePdfData)
    assert normalized.document.einvoice_code == "INV-2026-001"
    assert normalized.supplier.name == "Tenaga Nasional Berhad"
    assert normalized.buyer.name == "FINBRAIN SDN BHD"
    assert len(normalized.line_items) == 1
    assert normalized.totals.total_payable == Decimal("1240.00")

def test_normalize_legacy_kwargs_record():
    normalized = normalize_einvoice_data(
        supplier_name="Tenaga Nasional Berhad",
        supplier_tin="C1234567890",
        buyer_name="FINBRAIN Sdn Bhd",
        invoice_no="TNB-2026-88213",
        issue_date=date(2026, 8, 10),
        currency="MYR",
        tax_type="SST",
        tax_rate="6%",
        total_amount="1240.00",
        status="validated",
    )
    assert isinstance(normalized, EInvoicePdfData)
    assert normalized.supplier.name == "Tenaga Nasional Berhad"
    assert normalized.buyer.name == "FINBRAIN Sdn Bhd"
    assert normalized.document.einvoice_code == "TNB-2026-88213"
    assert normalized.totals.total_payable == Decimal("1240.00")
    assert len(normalized.line_items) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_einvoice_pdf.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.einvoice_pdf'`

- [ ] **Step 3: Implement data schema dataclasses and normalizer**

Create `backend/app/services/einvoice_pdf.py` with typed dataclasses and flexible `normalize_einvoice_data` function.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_einvoice_pdf.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/einvoice_pdf.py backend/tests/test_einvoice_pdf.py
git commit -m "feat(einvoice): add e-invoice PDF data schema and normalization logic"
```

---

### Task 2: Implement ReportLab Flowable Single-Page PDF Layout

**Files:**
- Modify: `backend/app/services/einvoice_pdf.py`
- Modify: `backend/tests/test_einvoice_pdf.py`

**Interfaces:**
- Produces:
  - `render_einvoice_pdf(data_or_record: dict | object | None = None, **kwargs) -> bytes`

- [ ] **Step 1: Write test for complete PDF rendering**

Add tests to `backend/tests/test_einvoice_pdf.py`:
```python
def test_render_einvoice_pdf_valid_bytes():
    pdf_bytes = render_einvoice_pdf(
        supplier_name="Tenaga Nasional Berhad",
        supplier_tin="C1234567890",
        buyer_name="FINBRAIN Sdn Bhd",
        invoice_no="TNB-2026-88213",
        issue_date="2026-08-10",
        currency="MYR",
        tax_type="SST",
        tax_rate="6%",
        total_amount="1240.00",
        status="validated",
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000

def test_render_einvoice_pdf_from_full_schema(sample_full_invoice_payload):
    pdf_bytes = render_einvoice_pdf(sample_full_invoice_payload)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_einvoice_pdf.py::test_render_einvoice_pdf_valid_bytes -v`
Expected: FAIL with `NameError: name 'render_einvoice_pdf' is not defined`

- [ ] **Step 3: Implement ReportLab PDF generator in `einvoice_pdf.py`**

Implement `render_einvoice_pdf` in `backend/app/services/einvoice_pdf.py` with:
1. Header band (left supplier identity, right e-INVOICE title & document metadata)
2. Gold accent horizontal rule (`#C9A227`)
3. Dark navy IRBM validation strip (`#16283A`) with UIN in monospace, validation status, and vector QR mock
4. Parties side-by-side boxes (Supplier Bill From & Buyer Bill To with `#1F3B57` header)
5. Itemised Details table with navy header, `#F2F4F6` zebra striping, and `#D9DCE1` cell borders
6. Totals block with right alignment and highlighted Navy `#1F3B57` Total Payable row
7. Payment information 2-column key-value grid
8. LHDN compliance disclaimer & footer notes

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/test_einvoice_pdf.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/einvoice_pdf.py backend/tests/test_einvoice_pdf.py
git commit -m "feat(einvoice): implement LHDN-compliant Malaysia e-Invoice PDF template layout"
```

---

### Task 3: Seed Module Integration & End-to-End Verification

**Files:**
- Modify: `backend/seed/generate_einvoice_pdf.py`
- Test: `backend/tests/test_einvoice_pdf.py`

**Interfaces:**
- Consumes: `app.services.einvoice_pdf.render_einvoice_pdf`
- Produces: backwards-compatible `render_einvoice_pdf` export from `backend/seed/generate_einvoice_pdf.py`

- [ ] **Step 1: Write integration test for seed re-export**

Add test in `backend/tests/test_einvoice_pdf.py`:
```python
def test_seed_module_reexport_compatibility():
    from seed.generate_einvoice_pdf import render_einvoice_pdf as seed_render
    pdf_bytes = seed_render(
        supplier_name="Grab Malaysia",
        supplier_tin="C9988776655",
        buyer_name="FINBRAIN Sdn Bhd",
        invoice_no="GRB-4471209",
        issue_date="2026-08-09",
        currency="MYR",
        tax_type="SST",
        tax_rate="0%",
        total_amount="86.40",
        status="submitted",
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
```

- [ ] **Step 2: Run test to verify current state**

Run: `pytest backend/tests/test_einvoice_pdf.py -v`

- [ ] **Step 3: Update `backend/seed/generate_einvoice_pdf.py` to forward to new service**

Update `backend/seed/generate_einvoice_pdf.py` to import and expose `render_einvoice_pdf` from `app.services.einvoice_pdf`.

- [ ] **Step 4: Run full backend test suite**

Run: `pytest backend/tests -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/seed/generate_einvoice_pdf.py backend/tests/test_einvoice_pdf.py
git commit -m "refactor(seed): re-export e-invoice PDF renderer from einvoice_pdf service"
```

---
