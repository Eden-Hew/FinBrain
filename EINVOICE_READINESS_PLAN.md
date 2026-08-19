# e-Invoice Readiness — basic-but-real implementation

## Context

We reviewed a feature-idea doc proposing three Attio-inspired features (Payment Chaser, Cash Flow Runway, e-Invoice Readiness). Investigation showed none of the backend infra they'd need exists yet — no Customer/Account entity, no Invoice table (the e-Invoice screen today is 100% frontend sample data), no cash-flow concept anywhere. Building all three would require a customer-identity-resolution layer first, which is out of scope for one pass.

The user chose to build **e-Invoice Readiness only** — it's the one feature that needs zero cross-source customer linking (it validates fields on invoice-shaped records that already exist as a concept) — at **"basic function done, with infra enabled for future full production"** depth: real DB tables, real endpoints, real (deterministic) validation logic, wired into the existing audit/approval/chat systems properly — but not a full production CRM-grade build (no real Telegram/email sending, no LLM-based fuzzy name matching yet, no full 55-field UBL schema).

Goal: a Finance/Owner/Compliance user can open a "Readiness Check" tab on e-Invoicing, see a real compliance score computed from real invoice records, drill into what's missing, and request a fix — which drafts an outreach message that goes through the existing Approvals confirm-before-send flow, not a direct send. The whole thing is also askable from Customer Intelligence chat, reusing the existing embed system, and every computed/decided step is hash-chained into the existing workflow audit log.

## Backend

**New tables** (mirror the `process_recommendations` migration exactly — `supabase/migrations/202608130002_track2_recommendations.sql` is the template for structure, indexes, RLS enable/force, revoke-from-anon/authenticated, and role-scoped policies):

- `einvoice_records` — id, `supplier_name`, `supplier_tin` (nullable), `buyer_name` (nullable), `invoice_no` (nullable), `issue_date` (nullable), `currency` (nullable), `tax_type` (nullable), `tax_rate` (nullable), `total_amount` (numeric), `status` (text, same 4 values as the frontend `EinvoiceStatus` enum: review/pending/submitted/validated), `source_record_id` (nullable FK-like link to `tokenized_content`, for future linkage — not enforced FK since not every record originates from ingestion), `created_at`, `updated_at`.
- `einvoice_outreach_drafts` — id, `einvoice_record_id` (FK → einvoice_records, cascade), `channel` (text, check in telegram/email), `draft_text`, `status` (text: draft/approved/rejected), `created_by_user_id`, `decided_by_user_id` (nullable), `created_at`, `decided_at` (nullable).

New migration file: `supabase/migrations/202608190001_einvoice_readiness.sql`. RLS: enable+force on both, revoke all from anon/authenticated, grant select/insert/update on both to `finbrain_app` only (no worker role needed — nothing here runs in a background worker). Policies: read open to any authenticated `finbrain_app` role (mirrors `process_recommendations`' broad select policy); insert on `einvoice_outreach_drafts` open to `finbrain_app`; update (the approve/reject transition) restricted `using (public.finbrain_role() = 'owner_director')` — same restriction pattern used for `process_recommendations` update at line ~191 of the reference migration.

**SQLAlchemy models** — add `EInvoiceRecord` and `EinvoiceOutreachDraft` classes to `backend/app/models.py`, following the exact field-typing conventions used by `ProcessRecommendation`/`RecommendationEvidence` (lines 344–412): `Mapped[...]`/`mapped_column`, `DateTime(timezone=True)` with `default=utcnow`/`onupdate=utcnow`, `ForeignKey(..., ondelete="CASCADE")`.

**Service** `backend/app/services/einvoice_readiness.py` (new file), modeled on `services/recommendations.py`'s structure but simpler — no LLM call needed since field-presence validation is deterministic:
- `compute_readiness(db) -> ReadinessResult`: query all `EInvoiceRecord` rows; for each, classify as **critical** (missing `supplier_tin` — blocks submission), **warning** (name-variant risk — normalize `supplier_name` via uppercase+strip-punctuation and flag any group with >1 distinct raw spelling, or missing a non-blocking field like `buyer_name`/`tax_type`), or **passing** (all required fields present, no mismatch flagged). Compute an aggregate score (`passing / total`). Call `write_workflow_event(db, event_type="einvoice_readiness_computed", actor_role=role.value, actor_ref=actor_ref, resource_type="einvoice_readiness", resource_id="workspace", event_payload={"score": ..., "critical": n, "warning": n, "passing": n})` — reuse `write_workflow_event` from `backend/app/services/workflow_audit.py:42` exactly as `recommendations.py:257` does. No new audit mechanism needed.
- `create_outreach_draft(db, record_id, channel, actor_role, actor_ref, created_by_user_id) -> EinvoiceOutreachDraft`: look up the record (404 via `LookupError` if missing — matches the `LookupError`→404 convention in `routes/recommendations.py:48`), build a deterministic template message (e.g. `f"Hi {supplier_name}, we're missing your Tax Identification Number (TIN) for invoice {invoice_no} (RM {total_amount}). Could you share it so we can complete MyInvois submission?"`), persist the draft row, fire `write_workflow_event(event_type="einvoice_outreach_drafted", ...)`, commit.
- `list_outreach_drafts(db) -> list[EinvoiceOutreachDraft]`: drafts with `status="draft"`, newest first (mirrors `list_recommendations`).
- `decide_outreach(db, draft_id, decision, actor_role, actor_ref) -> EinvoiceOutreachDraft`: only `draft → approved` / `draft → rejected` transitions allowed (else `ValueError` → 409, matching `recommendations.py:476`'s state-machine pattern); role check `if actor_role is not UserRole.OWNER_DIRECTOR: raise PermissionError(...)` defense-in-depth (mirrors `recommendations.py:202`); fire `write_workflow_event(event_type=f"einvoice_outreach_{decision}", ...)`. **Approving marks the draft `approved` — it does not actually send anything.** Real Telegram/email delivery integration is explicitly out of scope for this pass (documented below).

**Schemas** — add to `backend/app/schemas.py`, next to the recommendation schemas: `EInvoiceRecordResponse`, `EinvoiceReadinessCategory` (label, count, records: list of a light summary shape), `EinvoiceReadinessResponse` (score, next_deadline placeholder, categories), `EinvoiceOutreachDraftResponse`, `RequestFixPayload` (channel: Literal["telegram","email"]).

**Routes** `backend/app/routes/einvoice.py` (new file, registered in `backend/app/main.py` alongside the other `app.include_router(...)` calls):
- `GET /einvoice-readiness` — `require_roles(FINANCE_OPS, OWNER_DIRECTOR, COMPLIANCE)` (mirrors the `viewRecommendations` trio) → `compute_readiness`.
- `POST /einvoice-readiness/{record_id}/request-fix` — `require_roles(FINANCE_OPS, OWNER_DIRECTOR)` → `create_outreach_draft`.
- `GET /einvoice-outreach-drafts` — same trio as readiness view → `list_outreach_drafts`.
- `POST /einvoice-outreach-drafts/{id}/approve` / `/reject` — `require_roles(OWNER_DIRECTOR)` → `decide_outreach`. Exact try/except → HTTP status mapping as `routes/recommendations.py`'s `_decision` helper (PermissionError→403, LookupError→404, ValueError→409).

**Seed data** — extend `backend/seed/seed_data.py` (or add a small sibling script) to insert `EInvoiceRecord` rows directly (not through `ingest_canonical_record` — no enrichment/LLM needed for this table). Mirror the existing frontend sample suppliers for demo continuity (`frontend/src/data/sampleData.ts:235`) — e.g. keep "Office Supplies Sdn Bhd" missing its TIN, add a name-variant pair ("Acme Retail" / "ACME RETAIL SDN BHD") to demonstrate the warning category, and a few fully-valid records. Add the two new tables to `RESET_TABLES` in `seed_data.py` so `--reset` stays complete.

## Frontend

**`frontend/src/api/client.ts`**: add `fetchEinvoiceReadiness()`, `requestEinvoiceFix(recordId, channel)`, `fetchEinvoiceOutreachDrafts()`, `decideEinvoiceOutreach(id, decision)` + matching TS types, following the exact `fetchRecommendations`/`decideRecommendation` shape already there (line ~452–470).

**`frontend/src/lib/personas.ts`**: add `manageEinvoiceReadiness: boolean` to the `capabilities` shape (true for `finance_ops`/`owner_director`, false for `general_employee`/`compliance` — read access to the score itself can reuse `viewRecommendations` since the role trio matches exactly, so no new "view" capability is needed).

**`frontend/src/screens/Einvoice.tsx`**: add a second tab next to the existing table, reusing the `fb-role-switch`/`role="tablist"` visual pattern already used for the All/Mine filter (lines 59–62) — but this time actually swapping rendered content (new `activeTab` state), since no tab-switching mechanism exists in this file yet. New `ReadinessCheckPanel` component: fetches `fetchEinvoiceReadiness()` on mount, renders a score header (`X% Ready — N of M invoices pass`), three category cards (Critical/Warning/Passing counts, reusing the `.fb-kpi-tile`/color-token styling already established this session), and a click-to-expand table per category listing affected records with a "Request Fix" button that calls `requestEinvoiceFix` and shows an inline "Draft sent to Approvals" confirmation — no direct send, consistent with the Approvals-gating principle.

**`frontend/src/screens/Approvals.tsx`**: add `"outreach"` as a 5th `CardType` (line 14), plus matching `TYPE_ICON`/`TYPE_LABEL`/`TYPE_SUMMARY_LABEL` entries (lines 16–35). Add a new global CSS color token `--teal`/`--teal-soft` to `:root` and the dark-theme block in `styles.css` (same pattern as `--purple` was added earlier this session) so the outreach card gets its own distinct left-border/badge color rather than colliding with the existing `invoice` (blue) type. Fetch drafts via `fetchEinvoiceOutreachDrafts()` (new `useEffect`, mirrors the existing `recommendations` fetch at lines ~33–49), render with `TypeBadge type="outreach"` + `ConfirmApproveButton label="Approve & send"` → `decideEinvoiceOutreach(id, "approve")`, add an `outreach` entry to the `summary` chip array (lines 152–157) and the `isEmpty` check (lines 147–150).

**Customer Intelligence integration** (`frontend/src/components/embeds/ChatEmbeds.tsx` + `frontend/src/screens/Agents.tsx`):
- Add a real-data embed `EmbedEinvoiceReadiness` (new function in `ChatEmbeds.tsx`, following the existing embed conventions — `fb-rec-card`/`fb-rec-card-top`/`fb-status-pill` shell, local `useState`+`useEffect` fetching `fetchEinvoiceReadiness()` itself, matching how other embeds hold their own state).
- Add a new `RULES` entry: `{ test: ["myinvois","tin","readiness","compliance score","e-invoice ready"], text: "Here's your MyInvois readiness:", embed: () => <EmbedEinvoiceReadiness /> }`.
- Add a suggestion chip to `SUGGESTIONS` in `Agents.tsx` (line ~51): `"Which invoices need fixes before MyInvois submission?"`.
- **Required fix in `Agents.tsx`'s `send()`**: today, `embed` is only kept when the live `/query` call *fails* (line ~135 sets `embed = undefined` on success) — so a real-data embed would never show once the backend is healthy, which defeats the point. Change `send()` to independently check the keyword match (via a small new export from `ChatEmbeds.tsx`, e.g. `matchEmbed(text, lang, fallback)`) regardless of whether the live call succeeded, and attach the embed either way. This is a small, targeted change — not a rewrite of the intent-classification system (that stays backend-owned and untouched this pass).

## Explicit scope boundaries (documented, not built this pass)

- No real Telegram/email delivery — "Approve & send" marks the draft `approved` only. Wiring actual message delivery is a separate, higher-stakes change (real external side effects to real people) that needs its own explicit go-ahead.
- No LLM-drafted outreach message — the template is deterministic. Swapping in an LLM draft later can reuse the exact `morpheus_chat()` + schema-validation + offline-fallback pattern already proven in `services/recommendations.py:_generate_draft`.
- No full 55-field UBL/MyInvois schema — only the fields needed for the critical/warning distinction described above. Extending the table with more typed columns is additive, not a rewrite.
- The existing "All invoices" table/detail view (`Einvoice.tsx` main table, `EinvoiceDetail.tsx`) keeps using its current frontend sample data untouched — it is not rewired to the new backend table in this pass, to avoid scope creep into an already-working demo screen. Unifying them is natural follow-on work once CSV-ingestion → `EInvoiceRecord` linkage exists.
- No customer/account entity — `supplier_name` stays a plain string with simple normalization for the warning check, not a resolved identity. This is the seam future Payment Chaser/Cash Flow work would build on.

## Verification

1. Backend: run the new migration against the local Supabase/Postgres instance (or let SQLite's `initialize_local_schema()` pick up the new SQLAlchemy models automatically for local dev), run `python -m seed.seed_data` (or equivalent) to populate `einvoice_records`, then hit `GET /einvoice-readiness` and confirm the score/category breakdown matches the seeded data (one missing-TIN record → critical, one name-variant pair → warning).
2. Exercise the full request-fix → approve flow via `curl`/httpie against the new endpoints with each role to confirm the `require_roles` gating matches the plan (finance_ops can draft, cannot approve; owner_director can do both; general_employee gets 403 on read).
3. Confirm `GET /workflow-audit` (compliance role) shows the three new event types (`einvoice_readiness_computed`, `einvoice_outreach_drafted`, `einvoice_outreach_approved`/`_rejected`) with a valid hash chain.
4. Frontend: `npm run build`/`tsc -b` clean, then run the dev server and manually verify: Readiness tab renders real data, Request Fix creates a card in Approvals with the new teal styling, Approve & send moves it out of the pending list, and asking "Which invoices need fixes before MyInvois submission?" in Customer Intelligence renders the live embed (test with a real backend response, not just the offline-fallback path, to confirm the `send()` fix actually works).

---

## Note: what actually shipped beyond this plan

This document is the plan as originally written and approved. The implementation session that followed grew well past this scope through a series of follow-up requests:

- Real invoice PDFs generated and stored in a private Supabase Storage bucket, with signed-URL viewing from both the Readiness Check table and invoice detail pages.
- Manual invoice entry ("+ Add invoice") with PDF upload and LLM-based autofill (OCR text extraction → Morpheus structured-field extraction, with an offline regex fallback).
- The "All invoices" tab and detail view were unified onto the real `einvoice_records` table (originally scoped out — see "Explicit scope boundaries" above), including a real `uin` column and a working Approve & Submit to MyInvois endpoint.
- `einvoice_records` now syncs into the `tokenized_content` pipeline on create/approve, so Customer Intelligence chat can retrieve and cite e-invoice data through the same PII-protection pipeline as every other source.
- Two unrelated authentication bugs were found and fixed along the way: a login-form-wiping bug in `AuthProvider`, and a JWT clock-skew rejection bug in token verification.
- A missing Postgres RLS `UPDATE` policy on `einvoice_records` was discovered and fixed — without it, the real "Approve & Submit" button would have failed for every actual logged-in user.

All of the above is implemented, tested (122 backend tests, `tsc -b` and `ruff check` clean), verified end-to-end against the live database, and pushed to `main`.
