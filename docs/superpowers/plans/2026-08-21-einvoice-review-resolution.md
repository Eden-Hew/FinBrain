# E-Invoice Review Status Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement explicit compliance failure reasoning and actionable resolution workflows (Fix & Edit Details modal and Request Fix from Supplier) for review-status e-invoices.

**Architecture:** Extend backend readiness classification and record updating endpoints, enhance the invoice detail frontend with structured compliance callouts, field issue highlights, an inline edit modal with auto-promotion, and direct vendor outreach triggers.

**Tech Stack:** Python FastAPI, SQLAlchemy, ReportLab, React TypeScript, Vite.

## Global Constraints
- Target Malaysian LHDN MyInvois v4.6 compliance rules.
- Maintain existing RLS and role-based access control (`manageEinvoiceReadiness`, `approveEinvoiceSubmission`).
- Ensure all automated PDF regeneration and tokenized search synchronization occurs seamlessly on updates.

---

### Task 1: Backend Readiness Classification & Record Updates

**Files:**
- Modify: `backend/app/services/einvoice_readiness.py`
- Modify: `backend/app/routes/einvoice.py`
- Test: `backend/tests/test_einvoice_review_resolution.py`

**Interfaces:**
- Consumes: `EInvoiceUpdatePayload` from `app.schemas`
- Produces: `update_record` function in `app.services.einvoice_readiness` and `PATCH/PUT /einvoice-records/{record_id}` route returning updated `EInvoiceRecordResponse`

- [ ] **Step 1: Write the failing tests for record updates & auto-promotion**

```python
# backend/tests/test_einvoice_review_resolution.py
from datetime import date
from app.models import EInvoiceRecord
from app.schemas import EInvoiceUpdatePayload, UserRole
from app.services.einvoice_readiness import update_record, list_records, get_record

def test_update_record_promotes_review_to_pending(db_session, test_tenant_id):
    rec = EInvoiceRecord(
        tenant_id=test_tenant_id,
        supplier_name="Acme Corp",
        supplier_tin=None,
        buyer_name="FinBrain Corp",
        invoice_no="INV-REV-001",
        issue_date=date(2026, 8, 1),
        total_amount=1500.0,
        status="review",
    )
    db_session.add(rec)
    db_session.commit()

    # Verify reason is classified properly
    loaded = get_record(db_session, rec.id, test_tenant_id)
    assert "Missing supplier Tax Identification Number" in loaded.readiness_reason

    # Update with missing TIN
    payload = EInvoiceUpdatePayload(
        supplier_tin="C1234567890",
        buyer_name="FinBrain Sdn Bhd",
    )
    updated = update_record(
        db_session,
        rec.id,
        payload,
        role=UserRole.FINANCE_MANAGER,
        actor_ref="user-123",
        tenant_id=test_tenant_id,
    )
    assert updated.supplier_tin == "C1234567890"
    assert updated.status == "pending"
    assert "All required fields present" in updated.readiness_reason
```

- [ ] **Step 2: Run test to verify it fails or runs**

Run: `uv run pytest tests/test_einvoice_review_resolution.py -v`

- [ ] **Step 3: Implement `list_records` classification reasoning and update logic**

Ensure `list_records` evaluates `_classify(r, name_groups)` for each record in `backend/app/services/einvoice_readiness.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_einvoice_review_resolution.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/einvoice_readiness.py backend/app/routes/einvoice.py backend/tests/test_einvoice_review_resolution.py
git commit -m "feat(einvoice): add review reason classification and update resolution endpoint"
```

---

### Task 2: Frontend Compliance Callouts, Field Badges & Edit Modal

**Files:**
- Modify: `frontend/src/screens/EinvoiceDetail.tsx`
- Modify: `frontend/src/screens/Einvoice.tsx`

**Interfaces:**
- Consumes: `updateEinvoiceRecord` and `requestEinvoiceFix` from `../api/client`
- Produces: Interactive "Fix & Edit Details" modal and "Request Fix from Supplier" buttons with instant feedback

- [ ] **Step 1: Add Edit Modal & Compliance Notice in `RealEinvoiceDetail`**

Add state for `showEditModal`, `editForm`, `updating`, and `outreachState`.
Render prominent `fb-callout fb-callout-attn` with `record.readiness_reason`.
Badge missing fields in the extracted fields table.
Render full modal for editing invoice details and submitting via `updateEinvoiceRecord`.

- [ ] **Step 2: Add Edit Modal & Compliance Notice in mock `EinvoiceDetail`**

Mirror the same interactive experience in the mock detail view so both demo mock records and real DB records can be edited and promoted to `pending`.

- [ ] **Step 3: Verify frontend type-check & build**

Run: `npm run build` in `frontend` directory.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/screens/EinvoiceDetail.tsx frontend/src/screens/Einvoice.tsx
git commit -m "feat(einvoice): add review status compliance reason and fix action workflows"
```

---

### Task 3: Full Verification

- [ ] **Step 1: Run all backend pytest tests**

Run: `uv run pytest -v` in `backend` directory.

- [ ] **Step 2: Run frontend production build**

Run: `npm run build` in `frontend` directory.
