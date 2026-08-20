# Malaysia e-Invoice Payment Settlement & Official Receipt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the complete two-stage invoice settlement lifecycle: allow recording payments with a payment modal, update the e-Invoice PDF with a certified "PAID" badge, and generate an official Malaysian Payment Receipt (Resit Pembayaran) PDF with streaming download support.

**Architecture:** 
- Backend: ReportLab PDF generator additions in `app/services/einvoice_pdf.py` (`render_payment_receipt_pdf` and paid stamp in `render_einvoice_pdf`), and new receipt download endpoint `GET /einvoice-records/{id}/receipt/pdf`.
- Frontend: `RecordPaymentModal` component and dual view actions on `/einvoice-detail` using authenticated Blob URLs.

**Tech Stack:** Python 3.11+, ReportLab, FastAPI, React 19, TypeScript, Vite.

## Global Constraints
- Document format: Single-page A4 PDF (210mm x 297mm).
- Style Tokens: `#1F3B57` (Navy), `#16283A` (Dark Navy), `#C9A227` (Gold), `#F2F4F6` (Light Grey), `#10B981` (Paid Green).
- Typography: Helvetica / Helvetica-Bold for body/labels, Courier / Courier-Bold for UIN and transaction references.

---

### Task 1: Backend Payment Receipt PDF Generator & Paid Invoice Stamp

**Files:**
- Modify: `backend/app/services/einvoice_pdf.py`
- Modify: `backend/app/routes/einvoice.py`
- Test: `backend/tests/test_einvoice_pdf.py`

**Interfaces:**
- Produces:
  - `render_payment_receipt_pdf(data_or_record: Any, **kwargs) -> bytes`
  - `GET /einvoice-records/{record_id}/receipt/pdf` -> `Response(content=pdf_bytes, media_type="application/pdf")`

- [ ] **Step 1: Write failing unit test for `render_payment_receipt_pdf` and receipt route**

Add to `backend/tests/test_einvoice_pdf.py`:
```python
def test_render_payment_receipt_pdf_valid_bytes():
    from app.services.einvoice_pdf import render_payment_receipt_pdf
    receipt_bytes = render_payment_receipt_pdf(
        supplier_name="Tenaga Nasional Berhad",
        supplier_tin="C1234567890",
        buyer_name="FINBRAIN Sdn Bhd",
        invoice_no="TNB-2026-88213",
        issue_date="2026-08-10",
        paid_at="2026-08-15",
        currency="MYR",
        total_amount="1240.00",
        uin="MY29A8F1Q3RT",
    )
    assert isinstance(receipt_bytes, bytes)
    assert receipt_bytes.startswith(b"%PDF-")
    assert len(receipt_bytes) > 1000

def test_einvoice_receipt_pdf_route():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool
    from app.auth.dependencies import get_current_user
    from app.db import get_db
    from app.models import Base, EInvoiceRecord
    from app.routes.einvoice import router
    from tests.auth_support import principal
    from app.schemas import UserRole

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    record = EInvoiceRecord(
        supplier_name="Tenaga Nasional Berhad",
        buyer_name="FINBRAIN Sdn Bhd",
        invoice_no="TNB-2026-88213",
        issue_date=date(2026, 8, 10),
        paid_at=date(2026, 8, 15),
        currency="MYR",
        total_amount="1240.00",
        status="validated",
        uin="MY29A8F1Q3RT",
    )
    db.add(record)
    db.commit()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: principal(UserRole.FINANCE_OPS)

    client = TestClient(app)
    response = client.get(f"/einvoice-records/{record.id}/receipt/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_einvoice_pdf.py::test_render_payment_receipt_pdf_valid_bytes -v`
Expected: FAIL (ImportError / NameError)

- [ ] **Step 3: Implement `render_payment_receipt_pdf` and PAID stamp in `einvoice_pdf.py`**

In `backend/app/services/einvoice_pdf.py`:
- Add `paid_at` awareness to `TotalsInfo` and `render_einvoice_pdf` to show `"PAID • {paid_at}"` stamp.
- Implement `render_payment_receipt_pdf(data_or_record, ...)` generating the Official Payment Receipt PDF.
- Add `GET /einvoice-records/{record_id}/receipt/pdf` in `backend/app/routes/einvoice.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_einvoice_pdf.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/einvoice_pdf.py backend/app/routes/einvoice.py backend/tests/test_einvoice_pdf.py
git commit -m "feat(einvoice): implement official payment receipt PDF generator and receipt download route"
```

---

### Task 2: Frontend Record Payment Modal & Dual Document Actions

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/screens/EinvoiceDetail.tsx`

**Interfaces:**
- Produces:
  - `fetchEinvoiceReceiptBlob(recordId: number): Promise<Blob>` in `client.ts`
  - Record Payment modal & Payment Receipt viewing in `EinvoiceDetail.tsx`

- [ ] **Step 1: Add `fetchEinvoiceReceiptBlob` to `frontend/src/api/client.ts`**

In `frontend/src/api/client.ts`:
```typescript
export async function fetchEinvoiceReceiptBlob(recordId: number): Promise<Blob> {
  const response = await authenticatedFetch(`/einvoice-records/${recordId}/receipt/pdf`);
  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    throw new Error(errorBody.detail ?? `Failed to load payment receipt PDF (${response.status})`);
  }
  return response.blob();
}
```

- [ ] **Step 2: Implement Record Payment modal and receipt viewing in `frontend/src/screens/EinvoiceDetail.tsx`**

In `frontend/src/screens/EinvoiceDetail.tsx`:
- Add Record Payment modal for validated unpaid invoices.
- Add "Record Payment" button when `record.status === "validated" && !record.paid_at`.
- When `record.paid_at` is set, render:
  - Green `"PAID"` status pill with settlement date.
  - Action button `"View Invoice (Paid)"`.
  - Action button `"View Payment Receipt"` using `fetchEinvoiceReceiptBlob`.
- Support mock mode in `EinvoiceDetail` for `appState.einvoices`.

- [ ] **Step 3: Build frontend and verify TypeScript compliance**

Run: `npm run build`
Expected: PASS with 0 errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/screens/EinvoiceDetail.tsx
git commit -m "feat(frontend): add record payment modal and official payment receipt viewer to invoice detail"
```

---

### Task 3: Full Verification & Integration Testing

**Files:**
- Test: `backend/tests/test_einvoice_pdf.py`
- Verify: full test suites across backend and frontend

- [ ] **Step 1: Run full backend pytest suite**

Run: `uv run pytest -v` from `backend`
Expected: ALL 168+ tests PASS

- [ ] **Step 2: Run frontend build**

Run: `npm run build` from `frontend`
Expected: Build successfully created without warnings/errors

- [ ] **Step 3: Commit and clean up**

```bash
git status
```
---
