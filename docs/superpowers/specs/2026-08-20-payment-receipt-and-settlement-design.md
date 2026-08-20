# Malaysia e-Invoice Payment Settlement & Official Receipt Design Specification

**Date:** 2026-08-20  
**Status:** Approved  
**Target:** Two-Stage Invoice Lifecycle (Billing &rarr; Payment Settlement) with Official Payment Receipt PDF Generator  

---

## 1. Overview & Purpose
This document specifies the technical design for the payment settlement lifecycle of e-Invoices in FinBrain OS. When an e-Invoice is validated by LHDN MyInvois, buyers and finance operators can record payment settlement, generating both an official **Payment Receipt (Resit Pembayaran)** PDF and updating the **Tax Invoice** with a certified PAID settlement watermark and zero balance.

---

## 2. Document Specifications

### 2.1 Official Payment Receipt (Resit Pembayaran) PDF
Rendered as an A4 single-page document using ReportLab:
- **Header Band**: Supplier/Company branding, title `"OFFICIAL PAYMENT RECEIPT"` (`RESIT RASMI`), Receipt No., Receipt Date, and Payment Mode.
- **Gold Accent Divider**: `#C9A227` horizontal rule.
- **Payment Acknowledgment Strip**: Dark Navy container (`#16283A`) stating *"Payment Received With Thanks"* with the total amount paid in bold white text.
- **Payer Details (Received From)**: Buyer Name, TIN, Registration No., Address.
- **Invoice & MyInvois Reference**: Original Invoice Number, Issue Date, and validated MyInvois UIN.
- **Settlement Breakdown Table**: Total Invoiced Amount, Total Paid, and Balance Outstanding (RM 0.00).
- **Footer**: Verification disclaimer and FinBrain OS document reference.

### 2.2 Paid Watermark on e-Invoice PDF
When `paid_at` is present on an e-Invoice:
- The Totals block renders a prominent green/gold settlement badge: `"PAID &bull; {paid_at}"`.
- The Totals summary adds a `"Balance Due: RM 0.00"` indicator.

---

## 3. Backend Architecture & Endpoints

### 3.1 Service Layer (`backend/app/services/einvoice_pdf.py`)
- `render_payment_receipt_pdf(data_or_record: Any, **kwargs) -> bytes`: Renders the official Payment Receipt PDF and returns bytes.
- `render_einvoice_pdf(data_or_record: Any, **kwargs) -> bytes`: Enhanced with `paid_at` awareness for the paid settlement badge.

### 3.2 API Layer (`backend/app/routes/einvoice.py`)
- `POST /einvoice-records/{record_id}/mark-paid`: Records settlement with payload `{ "paid_at": "YYYY-MM-DD", "payment_method": "string", "payment_reference_no": "string" }`.
- `GET /einvoice-records/{record_id}/receipt/pdf`: Streams the Payment Receipt PDF as `application/pdf`.

---

## 4. Frontend User Experience (`frontend/src/screens/EinvoiceDetail.tsx`)

1. **Unpaid Validated Invoices (`status === "validated"` and `!paid_at`)**:
   - Displays **"Record Payment"** action button.
   - Clicking opens the **Payment Details Modal** (Payment Date picker, Payment Method selector: Bank Transfer, DuitNow, Cheque, Card, Cash, and Reference Number).
2. **Paid Invoices (`paid_at` is set)**:
   - Displays a green **"PAID"** status badge in the header.
   - Document section presents two actions:
     - **"View Invoice (Paid)"**: Opens the e-Invoice PDF with the PAID stamp.
     - **"View Payment Receipt"**: Opens the official Payment Receipt PDF via client-side Blob URL.

---

## 5. Verification & Testing
- Unit tests for `render_payment_receipt_pdf` in `backend/tests/test_einvoice_pdf.py`.
- Integration tests for `GET /einvoice-records/{id}/receipt/pdf` and `POST /einvoice-records/{id}/mark-paid`.
- Full backend pytest suite (`pytest`) and frontend production build (`npm run build`).
