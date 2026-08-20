# Design Specification: E-Invoice Review Status Resolution and Action Workflows

**Date:** 2026-08-21  
**Status:** Approved  
**Author:** opencode & FinBrain Team  

## 1. Background & Problem Statement
When invoices are scanned or ingested into FinBrain, some lack mandatory compliance fields (such as a missing Supplier Tax Identification Number `supplier_tin`, missing buyer details, or inconsistent supplier business names) required by LHDN MyInvois v4.6.

Previously, flagged invoices entered a `review` status where approval was blocked, but the UI provided limited interactive capability to resolve the issues directly. Users needed clearer explanations of the exact compliance failure reasons and intuitive actions to either fix the fields themselves or request vendor correction.

## 2. Goals & Objectives
1. **Explicit Reason Display**: Clearly explain why an invoice is in `review` status on both the list/readiness view and the invoice detail screen.
2. **Interactive Field Highlighting**: Visually flag missing or inconsistent fields within the *Extracted Fields* breakdown.
3. **Self-Serve Fix Action ("Fix & Edit Details")**: Provide a modal allowing users (with appropriate permissions) to edit and provide missing fields (TIN, buyer name, tax type, etc.). On save:
   - Persist changes to the database.
   - Re-evaluate readiness and promote status to `pending` if compliance conditions are satisfied.
   - Automatically regenerate the PDF invoice and sync the tokenized search mirror.
   - Immediately unlock the **"Approve & Submit to MyInvois"** action.
4. **Vendor Outreach Action ("Request Fix from Supplier")**: Provide a single-click action to generate an automated outreach message draft in the Approvals queue.

## 3. Architecture & Data Flow

### 3.1 Backend Service Changes (`backend/app/services/einvoice_readiness.py`)
- **Reason Classification in `list_records` & `get_record`**:
  Compute dynamic reasons via `_classify(record, name_groups)` and return them in `readiness_reason`.
- **Record Update Endpoint (`PATCH /einvoice-records/{id}`)**:
  - Accept `EInvoiceUpdatePayload` (supplier, buyer, invoice metadata, remittance, and tax fields).
  - When `supplier_tin` is provided on a `review` record, promote `status` from `review` to `pending`.
  - Re-render the e-invoice PDF (`render_einvoice_pdf`) and overwrite the stored document in storage.
  - Record an audit workflow event `einvoice_record_updated`.
  - Sync the tokenized content mirror for search/chat intelligence.

### 3.2 Frontend Experience (`frontend/src/screens/EinvoiceDetail.tsx`)
- **Compliance Callout**:
  Render a high-visibility callout box displaying `record.readiness_reason` with specific issue bullets when `status === "review"`.
- **Field Badges**:
  In the *Extracted Fields* list, display `Missing — Action Required` in warning text whenever `supplier_tin` or other critical fields are missing.
- **Action Buttons in Header**:
  - `Fix & Edit Details`: Opens pre-filled edit modal.
  - `Request Fix from Supplier`: Calls `requestEinvoiceFix(recordId, "telegram")` with loading and success states.
- **Edit Modal**:
  - Clean inputs for `supplier_name`, `supplier_tin`, `buyer_name`, `invoice_no`, `issue_date`, `due_date`, `tax_type`, `tax_rate`, `total_amount`, and remittance details.
  - Submits to `updateEinvoiceRecord` and refreshes the local record.

## 4. Security & Role Permissions
- Only users with `manageEinvoiceReadiness` or `approveEinvoiceSubmission` permissions (e.g. Finance Managers, Admins) can trigger record edits, approval, and outreach.
- All modifications write structured workflow audit events with actor attribution and tenant isolation.

## 5. Testing & Verification
- Unit and integration tests in pytest verifying:
  - `update_record` correctly updates fields and promotes `review` $\rightarrow$ `pending` when `supplier_tin` is populated.
  - PDF re-rendering upon update.
  - `list_records` and `get_record` return accurate readiness reasons.
- Frontend test and build verification (`npm run build`).
