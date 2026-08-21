# Telegram Customer Onboarding and Overdue Reminder Implementation Plan

**Goal:** Add privacy-safe Telegram customer onboarding, endpoint-based customer reconciliation, invoice association, and governed overdue reminders while preserving FinBrain's Supabase tenancy, RLS, vault, idempotency, and audit contracts.

**Architecture:** Reuse `customer_endpoints`, `outreach_actions`, `outreach_evidence`, `token_vault`, and the existing customer/invoice domains. Introduce a deep endpoint-resolution module used by both email and Telegram adapters, a durable Telegram onboarding state machine, and a channel-neutral outbound dispatcher with SMTP and Telegram adapters.

**Design:** `docs/superpowers/specs/2026-08-21-telegram-customer-onboarding-overdue-reminders-design.md`

---

## Global constraints

- Add forward migrations only; never edit applied migration files.
- Keep migration, `backend/app/models.py`, `backend/scripts/check_supabase.py`, `SUPABASE_ARCHITECTURE.md`, and `SUPABASE_SCHEMA_REFERENCE.md` synchronized.
- Use TDD for each task.
- Raw PII and raw Telegram identifiers exist only in trusted process memory and encrypted vault entries.
- All worker operations call `set_worker_context()` with a real tenant.
- Do not weaken forced RLS or grant browser table access.
- Commit each task atomically after its focused tests pass.

---

### Task 1: Add schema migration and model mappings

**Files:**

- Create: `supabase/migrations/202608210001_telegram_customer_onboarding_and_reminders.sql`
- Modify: `backend/app/models.py`
- Modify: `backend/scripts/check_supabase.py`
- Modify: `SUPABASE_SCHEMA_REFERENCE.md`
- Modify: `SUPABASE_ARCHITECTURE.md`
- Test: `backend/tests/test_database_portability.py`

- [ ] Write failing SQLite model tests for the new columns, tables, uniqueness rules, status checks, and restrictive foreign keys.
- [ ] Add `delivery_token` and `last_interaction_at` to `customer_endpoints`.
- [ ] Add `telegram_onboarding_sessions` and `tenant_outreach_policies`.
- [ ] Tenant-scope `telegram_update_receipts` with additive nullable columns, deterministic default-tenant backfill, then `NOT NULL` and tenant-aware indexes/policies.
- [ ] Add buyer contact tokens to `einvoice_records`.
- [ ] Extend `outreach_actions` for system origin, invoice lineage, scheduling, and actor provenance.
- [ ] Add grants, enabled/forced RLS, tenant-aware application/worker policies, timestamp triggers, checks, and queue indexes.
- [ ] Update the SQLAlchemy mappings and Supabase checker in the same change.
- [ ] Update both Supabase Markdown contracts to the new live target schema.
- [ ] Run portability tests and apply the migration to a disposable Supabase project; run `scripts.check_supabase`.

### Task 2: Extract shared endpoint-resolution module

**Files:**

- Create: `backend/app/services/customer_endpoint_resolution.py`
- Modify: `backend/app/integrations/email_connector/identity.py`
- Test: `backend/tests/test_customer_endpoint_resolution.py`
- Test: `backend/tests/test_email_reconciliation.py`

- [ ] Define `EndpointEvidence` and `EndpointResolutionResult` with a small interface.
- [ ] Write failing tests for new profile creation, existing endpoint reuse, revoked endpoints, cross-customer conflicts, duplicate retries, and tenant isolation.
- [ ] Move generic token protection, endpoint uniqueness, provisional customer creation, record linking, and audit behavior behind `resolve_customer_endpoint()`.
- [ ] Keep email-specific sender extraction and identity claims in the email adapter.
- [ ] Replace email-first profile creation with the shared module without changing existing behavior.
- [ ] Run all email connector and customer identity tests.

### Task 3: Add durable customer-facing Telegram onboarding

**Files:**

- Create: `backend/app/integrations/telegram/onboarding.py`
- Modify: `backend/app/integrations/telegram/handlers.py`
- Modify: `backend/app/integrations/telegram/bot.py`
- Modify: `backend/app/integrations/telegram/keyboards.py`
- Modify: `backend/app/integrations/telegram/receipts.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_telegram_onboarding.py`
- Test: `backend/tests/test_telegram_adapter.py`
- Test: `backend/tests/test_telegram_auth.py`

- [ ] Add a customer mode that accepts private users without granting operator capture permissions.
- [ ] Preserve the existing operator-only `/capture` authorization path.
- [x] Persist `/start` privacy acknowledgement, name, Gmail, phone sharing, reconciliation, message-ready,
  cancellation, and completion transitions before responding.
- [ ] Enforce the guided order: name, valid Gmail address, sender-owned Telegram phone contact,
  then business message. Reject out-of-order input without advancing the session.
- [ ] Combine name, Gmail, phone, Telegram user ID, and Telegram chat ID into exactly one canonical
  `customer_onboarding_profile` record after all required fields are present.
- [ ] Request phone via a private-chat reply keyboard and reject contacts whose `user_id` does not match the sender.
- [ ] Protect Telegram user ID, chat ID, username, email, phone, and display-name evidence through the vault.
- [ ] Call the shared endpoint resolver and attach verified Telegram and phone endpoints plus the
  observed Gmail endpoint to the same customer.
- [ ] Link the unified profile `tokenized_content` row with
  `match_basis = 'telegram_onboarding_profile'`, then run normal protected summary/embedding
  enrichment and customer-attention refresh.
- [ ] After reconciliation, prompt for the first business message and ingest every accepted
  message as a separate `customer_message` record linked with
  `match_basis = 'verified_telegram_endpoint'`.
- [ ] Keep the protected record, customer, endpoints, and record link committed when enrichment
  fails; retry only enrichment from persisted protected content.
- [ ] Make receipt processing and onboarding reconciliation retryable after any commit or restart.
- [ ] Add `/profile` and `/privacy` responses that expose only masked endpoint values.
- [ ] Test duplicate updates, malformed email, forwarded contact, blocked/revoked endpoint, expired session, and tenant isolation.
- [ ] Test that `/start`, individual onboarding answers, and bot-authored prompts do not create
  separate knowledge records; the completed identity bundle creates exactly one unified profile
  record, and subsequent customer messages create separately linked knowledge records.

### Task 4: Protect and resolve invoice buyer endpoints

**Files:**

- Modify: `backend/app/services/einvoice_readiness.py`
- Modify: `backend/app/services/entity_resolution.py`
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/test_einvoice_customer_resolution.py`
- Test: `backend/tests/test_einvoice_review_resolution.py`

- [ ] Write failing tests for buyer email/phone tokenization and exact endpoint resolution.
- [ ] Persist only protected buyer contact tokens on `einvoice_records`.
- [ ] Resolve `buyer_customer_id` only when one tenant-owned, non-revoked endpoint matches.
- [ ] Preserve an existing explicit customer link unless reviewed evidence authorizes a change.
- [ ] Record unresolved and conflicting matches as workflow audit events without raw endpoint values.
- [ ] Recalculate customer attention after a new invoice link.
- [ ] Add an idempotent backfill script for existing invoices whose protected source contains a uniquely attributable buyer endpoint.

### Task 5: Generalize governed outreach delivery

**Files:**

- Create: `backend/app/integrations/outbound/types.py`
- Create: `backend/app/integrations/outbound/dispatcher.py`
- Create: `backend/app/integrations/telegram/sender.py`
- Modify: `backend/app/integrations/email_connector/sender.py`
- Modify: `backend/app/services/outreach.py`
- Test: `backend/tests/test_outbound_dispatcher.py`
- Test: `backend/tests/test_telegram_sender.py`
- Test: `backend/tests/test_email_sender.py`

- [ ] Define the channel-neutral delivery interface and result types.
- [ ] Adapt existing SMTP sending without changing its state-transition semantics.
- [ ] Add Telegram delivery using decrypted `delivery_token` only inside the worker.
- [ ] Claim work transactionally and idempotently; increment attempts before provider calls.
- [ ] Re-read customer, endpoint, identity review, and invoice eligibility immediately before sending.
- [ ] Mark `sent` only after Telegram confirms success; store only an opaque/hash provider reference.
- [ ] Implement failed and delivery-unknown recovery without blind resend.
- [ ] Write workflow/disclosure audit events with protected or opaque payloads only.

### Task 6: Plan overdue reminder actions

**Files:**

- Create: `backend/app/services/overdue_reminders.py`
- Create: `backend/app/services/overdue_reminders_runner.py`
- Modify: `backend/app/services/health.py`
- Modify: `backend/app/routes/health.py`
- Modify: `backend/app/config.py`
- Modify: `docker/entrypoint.sh`
- Modify: `scripts/demo_processes.ps1`
- Test: `backend/tests/test_overdue_reminders.py`

- [ ] Write failing tests for eligibility, grace period, paid invoices, missing customers, unverified/revoked endpoints, identity conflicts, maximum reminders, and tenant isolation.
- [ ] Implement deterministic reminder stages and idempotency keys.
- [ ] Create protected outreach content and invoice evidence without sending directly.
- [ ] Respect owner-controlled tenant policy: pending approval by default, direct approval only when explicitly enabled.
- [ ] Reconcile a prior action rather than duplicating it after partial failure.
- [ ] Add a tenant-iterating worker using `set_worker_context()` separately for each tenant.
- [ ] Add heartbeat, batch size, interval, and graceful failure behavior.

### Task 7: Add owner controls and operational visibility

**Files:**

- Modify: `backend/app/routes/outreach.py`
- Modify: `backend/app/schemas.py`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/screens/Approvals.tsx`
- Modify: `frontend/src/screens/Customers.tsx`
- Modify: `frontend/src/screens/EinvoiceDetail.tsx`
- Test: backend outreach/policy route tests

- [ ] Add authenticated policy read and owner-only update operations through FastAPI.
- [ ] Display Telegram endpoints only as masks and show verification/revocation state.
- [ ] Show reminder origin, invoice lineage, scheduled time, attempts, and failure state in approvals.
- [ ] Allow owners to approve/reject reminders when policy requires approval.
- [ ] Show sent reminder history on customer and invoice views without exposing raw destinations.
- [ ] Add explicit confirmation before enabling automatic reminder sending.
- [ ] Run frontend typecheck, lint, and production build.

### Task 8: Supabase and end-to-end verification

**Files:**

- Test: focused and full backend suites
- Verify: disposable Supabase project
- Update: `TESTING_GUIDE.md`
- Update: `README.md`

- [ ] Run duplicate/retry tests at every commit boundary in onboarding and delivery.
- [ ] Run PostgreSQL tests as `finbrain_app` and `finbrain_worker` for correct and incorrect tenants.
- [ ] Verify `anon` and `authenticated` cannot access new tables.
- [ ] Verify forced RLS, grants, indexes, checks, triggers, and worker queue policies with `scripts.check_supabase`.
- [ ] Verify raw Telegram IDs, usernames, email, and phone do not appear in application tables, logs, audit payloads, or protected metadata.
- [ ] Verify key rotation can rotate every new vault-backed endpoint without changing endpoint identity tokens.
- [ ] Exercise: new Telegram user -> provisional profile -> invoice match -> overdue action -> approval/policy -> Telegram delivery -> paid invoice suppresses future reminders.
- [ ] Run full backend tests and lint, frontend build/lint, `supabase migration list`, and `git diff --check`.
- [ ] Update operator/customer setup and recovery procedures.

## Completion definition

The feature is complete only when the end-to-end flow passes against PostgreSQL/Supabase with forced RLS, duplicate updates and worker restarts remain idempotent, raw contact data is absent outside the vault, and an overdue invoice can reach only the verified Telegram endpoint belonging to its tenant-scoped customer.
