# FinBrain Demo Database Preparation

This reference complements `SUPABASE_ARCHITECTURE.md` and
`SUPABASE_SCHEMA_REFERENCE.md`. It records the live-schema audit performed on
2026-08-21 and defines which data must exist before a complete demo.

## Safety contract

- `python -m seed.demo_session` is read-only and is the default.
- `python -m seed.demo_session --apply` is idempotent and non-destructive. It
  inserts or refreshes only deterministic, seed-owned fixtures.
- `python -m seed.demo_session --apply --reset --yes` clears application data,
  preserves migrations, the tenant, and Supabase Auth role assignments, then
  builds a reproducible clean demo database.
- Stop the backend and all email/Telegram workers before `--apply` to avoid
  races while fixtures are being assembled.
- The preparer never fabricates Supabase Auth users, usable Telegram chat IDs,
  vault key rotations, or provider delivery receipts.
- A real, completed Telegram `/start` onboarding is required. Reminder fixtures
  remain `pending_approval`, so a live worker cannot send them automatically.
  Clean-reset mode creates a clearly marked, non-deliverable protected Telegram
  fixture so onboarding, linking, drafting, and approval screens work immediately.
  Actual Telegram delivery requires a real user to complete `/start` afterward.
- An existing tenant outreach policy is owner-controlled. The preparer will not
  overwrite an incompatible policy; it fails with an actionable message.
- The old `python -m seed.seed_data --reset --yes` path is destructive and is
  not required for normal demo preparation.

Run from `backend`:

```powershell
..\.venv\Scripts\python.exe -m seed.demo_session
..\.venv\Scripts\python.exe -m seed.demo_session --apply
..\.venv\Scripts\python.exe -m seed.demo_session --apply --reset --yes
..\.venv\Scripts\python.exe -m seed.demo_session
```

## Live remote baseline

The linked remote Supabase was inspected through PostgreSQL catalogs and the
project's schema checker. All migrations from `202608110001` through
`202608210002` are applied. PostgreSQL is 17.6 and pgvector is 0.8.2. All 34
application tables, documented columns, constraints, indexes, triggers, forced
RLS policies, the Auth hook, and the expected database roles are present.

The read-only readiness run found 7 of 13 feature scenarios ready. Existing
coverage includes all four application roles, eight protected source systems,
linked customer profiles, verified email and Telegram endpoints, two completed
Telegram onboarding sessions, the e-invoice lifecycle, and persistent chat
citations. Missing coverage is a structured CSV batch, approval/reply outreach
states, an approval-safe reminder policy and overdue Telegram reminder, an email
reply correlation, and an implemented recommendation.

## Table-by-table seed responsibility

| Table | Purpose in the system | Demo preparation responsibility |
|---|---|---|
| `tenants` | Tenant boundary for all business data | Validate the default tenant; never replace it. |
| `user_roles` | Backend-authoritative Supabase Auth role mapping | Validate one active user for each of the four roles; never invent Auth IDs. |
| `tokenized_content` | Protected searchable records and embeddings | Seed all connector-neutral sample sources, e-invoice mirrors, customer evidence, and structured rows through ingestion services. |
| `token_vault` | Encrypted token-to-value mappings | Derived only through tokenization; never insert plaintext or handcrafted ciphertext. |
| `protected_token_registry` | Safe token type and mask registry | Derived only through tokenization. |
| `vault_key_versions` | Active/retired wrapping key metadata | Validate one active key; key administration is operational, not demo seed data. |
| `vault_rotation_jobs` | Rotation workflow state | Do not seed. Exercise only through the real rotation workflow when specifically demonstrating it. |
| `audit_log` | Hash-chained protected-ingestion audit | Derived by ingestion and vault services; never synthesize rows. |
| `workflow_audit_log` | Hash-chained business-workflow audit | Derived by outreach/recommendation/demo workflow operations. |
| `integration_status` | Connector/worker health | Connector-owned. Validate health while services run; do not forge heartbeats. |
| `email_sync_state` | Incremental IMAP cursor | Connector-owned. Preserve the live mailbox cursor. |
| `email_ingestion_receipts` | HMAC-addressed inbound-email receipt | Preserve live receipts; add one deterministic, non-provider historical correlation fixture without a raw message ID. |
| `email_reply_correlations` | Links an inbound reply to sent outreach | Add one historical, seed-owned correlated reply. |
| `structured_ingestion_batches` | Structured upload progress and counts | Ingest `demo/chat_upload_invoice_register.csv` through the production service. |
| `conversations` | Protected chat session and optional customer context | Add one deterministic owner conversation demonstrating persistent evidence. |
| `conversation_turns` | Protected questions, answers, briefs, and modes | Add one SQL-first source-listing turn. |
| `conversation_turn_citations` | Stable SOURCE-N evidence mapping | Cite three ready protected records from the demo turn. |
| `process_recommendations` | Governed improvement proposals | Ensure one proposed and one implemented seed-owned recommendation. |
| `recommendation_evidence` | Protected source evidence for a recommendation | Link each seeded recommendation to ready records. |
| `recommendation_decisions` | Owner approval/rejection/implementation history | Add approved and implemented decisions for the historical fixture. |
| `customers` | Canonical cross-source customer profile | Ensure the Luma email fixture and reuse a real confirmed Telegram customer. |
| `customer_aliases` | Protected organization/name aliases | Derived through entity resolution for seeded customer content. |
| `customer_record_links` | Verified customer-to-evidence graph | Derive verified links for customer email and e-invoice evidence. |
| `customer_attention_snapshots` | Point-in-time customer priority | Derived through attention recalculation; never manually score. |
| `customer_attention_signals` | Explainable components of an attention score | Derived with snapshots from linked evidence and outstanding invoices. |
| `customer_endpoints` | Protected email/phone/Telegram destinations | Verify the seed email endpoint; clean mode adds a non-deliverable Telegram fixture and live onboarding adds real endpoints. |
| `telegram_onboarding_sessions` | Durable `/start` collection state | Clean mode exercises the real onboarding pipeline with marked synthetic values; actual delivery requires a later real session. |
| `tenant_outreach_policies` | Owner-controlled reminder policy | Create only when absent, enabled with `require_approval=true`; never overwrite. |
| `customer_identity_claims` | Reviewable inbound identity evidence | Derived by email/Telegram ingestion. Preserve conflicts for identity-review demos. |
| `outreach_actions` | Governed multichannel draft/approval/delivery state | Add a finance email pending approval, a safe Telegram overdue reminder, and one historical replied email. Never seed queueable Telegram approval. |
| `outreach_evidence` | Evidence attached to outbound actions | Link only verified customer records that are ready for reasoning. |
| `telegram_update_receipts` | Telegram update deduplication and status | Connector-owned; never fabricate provider update IDs. |
| `einvoice_records` | Operational e-invoice and payment lifecycle | Upsert every documented base invoice independently, even in a populated DB; add a dated overdue invoice tied to the real Telegram customer. |
| `einvoice_outreach_drafts` | Legacy invoice outreach draft lifecycle | Add isolated draft/approved/rejected historical fixtures for legacy UI coverage. |

## Feature coverage after apply

The prepared dataset supports protected multi-source `/ask`, stable citations
across turns, customer-context intelligence, customer endpoint selection, email
and Telegram response drafting, finance submission plus owner approval, overdue
invoice reminder planning, AR/e-invoice readiness views, structured CSV upload,
email reply correlation, customer attention, process recommendations and owner
decisions, audit-chain inspection, and connector health display.

Operational demonstrations still require their real dependencies: Supabase Auth
sessions for each persona, configured provider credentials, a running worker for
actual delivery, and valid vault key material. Email/Telegram connector receipts
and sync cursors are cleared in clean-reset mode, so workers restart ingestion
against the configured demo mailbox and bot. The synthetic Telegram fixture must
never be approved for real delivery; a real `/start` onboarding supersedes it for
an outbound delivery demonstration.
