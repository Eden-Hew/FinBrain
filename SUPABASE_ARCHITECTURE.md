# FinBrain Supabase Architecture and Change Guardrails

This document is the contributor-facing contract for FinBrain's Supabase database. It describes
the schema verified against the live project on **20 August 2026**, the boundaries that application
code depends on, and the procedure required for every database change.

For the live column-by-column disaster-recovery snapshot, see
[`SUPABASE_SCHEMA_REFERENCE.md`](SUPABASE_SCHEMA_REFERENCE.md).

The live verification command reported PostgreSQL 17.6, pgvector 0.8.2, `vector(768)`, the HNSW
index, all expected tables and columns, forced RLS, versioned vault security, append-only audit
triggers, and the email-first customer/outreach schema as present.

## Sources of truth

Use these sources together, in this order:

1. `supabase/migrations/*.sql` is the authoritative history for PostgreSQL schema, grants, RLS,
   functions, triggers, indexes, constraints, and data backfills.
2. `backend/app/models.py` is the SQLAlchemy mapping used by application code. It must match the
   final migrated schema.
3. `backend/scripts/check_supabase.py` is the deployed-schema contract. Extend it whenever a new
   table, required column, index, policy, trigger, or extension becomes mandatory.
4. `backend/app/db.py` owns application and worker RLS context. Do not reproduce role switching in
   routes or workers.

SQLite is only a local portability and test backend. `Base.metadata.create_all()` is intentionally
limited to SQLite and does not reproduce PostgreSQL RLS, grants, triggers, pgvector, or migration
backfills. Passing SQLite tests alone does not prove a Supabase migration is correct.

## Trust and data flow

```text
Browser
  | Supabase email/password authentication; publishable key only
  | access token containing user_role and tenant_id
  v
FastAPI trusted boundary
  | verifies the asymmetric Supabase JWT locally
  | sets app.user_id, app.user_role, app.actor_ref, app.tenant_id
  | enters the non-BYPASSRLS finbrain_app database role
  v
Canonical protected ingestion
  | raw content exists in application memory only
  | PII detection -> tenant-scoped deterministic tokens
  | ciphertext -> token_vault
  | protected text/metadata -> tokenized_content
  v
Protected enrichment and retrieval
  | external models receive protected values only
  | SQL-first filters/counts/listings and protected vector search
  | role-authorized detokenization occurs only in the backend
  v
Customer context / recommendations / governed outreach / audit

Background workers
  | set app.actor_ref and app.tenant_id
  | enter the non-BYPASSRLS finbrain_worker database role
  v
Email, Telegram, enrichment, attention, recommendation, and vault-rotation work
```

The frontend must never receive the database password, service-role key, token root secret, vault
keys, or raw vault ciphertext. It uses the Supabase project URL and publishable key only for Auth;
business data and function calls go through FastAPI.

## Tenancy, authentication, and RLS

- `tenants` is the organization boundary. The current proof of concept uses the default tenant
  `00000000-0000-0000-0000-000000000001`.
- `user_roles` maps an Auth user to a tenant-owned FinBrain role. The current roles are
  `general_employee`, `finance_ops`, `owner_director`, and `compliance`.
- `custom_access_token_hook(jsonb)` adds `user_role` and `tenant_id` to new Supabase access tokens.
- FastAPI treats the verified token as identity input, then loads backend-owned authorization and
  calls `set_rls_context()`.
- Workers call `set_worker_context()` with a real tenant for tenant work. A blank tenant is reserved
  for genuinely global work such as vault-key rotation.
- `finbrain_app` and `finbrain_worker` do **not** have `BYPASSRLS`.
- RLS is enabled and forced on protected tables. Direct `anon` and `authenticated` table grants are
  revoked. Policies use the transaction-local `app.*` context.
- `backend/app/db.py` restores context and `SET LOCAL ROLE` after every commit-created transaction.
  Removing that event hook causes workers and multi-commit request flows to fail or use the wrong
  authorization context.

Do not solve an RLS error by granting broad access, disabling `FORCE ROW LEVEL SECURITY`, using the
Supabase service role from the frontend, or connecting application traffic as a bypass role. Fix
the missing tenant/actor context or the narrowly scoped policy.

## Schema domains

### Protected knowledge and vault

| Table | Responsibility | Important invariant |
|---|---|---|
| `tokenized_content` | Protected source text, summary, structured summary, safe metadata, status, and `vector(768)` embedding | Never stores known raw PII; `source_record_id` is stable and opaque |
| `protected_token_registry` | Safe lookup metadata for deterministic tenant-scoped tokens | Contains no plaintext secret |
| `token_vault` | AES-256-GCM ciphertext, masked display value, role ACL, and key version | Plaintext is never stored; reads remain role-gated |
| `vault_key_versions` | Wrapped random generation keys and lifecycle state | A generation cannot be retired while any vault row still uses it |
| `vault_rotation_jobs` | Resumable rotation progress and status | Rotation re-encrypts vault rows; it does not change stable tokens |

Tokens are deterministic HMAC identifiers scoped by tenant, which supports matching the same
entity across protected records. Vault encryption is versioned separately: the root secret unwraps
a generation key, and each token receives an HKDF-derived encryption key. Key rotation creates a
new generation and re-encrypts ciphertext in batches. Never retire or delete the old generation
before every referenced row has moved and the rotation job has completed.

### Ingestion and connector durability

| Table | Responsibility |
|---|---|
| `structured_ingestion_batches` | Idempotent structured-file batch status and row counts |
| `telegram_update_receipts` | Durable Telegram update deduplication and ingestion status |
| `email_sync_state` | IMAP cursor, mailbox reference, sync health, and last synchronization |
| `email_ingestion_receipts` | HMAC-addressed email delivery receipt, protected source reference, customer/outreach correlation status |
| `email_reply_correlations` | Evidence that one protected inbound email matched one governed outbound action |
| `integration_status` | Heartbeats for API and background workers |

A connector receipt means the delivery was observed; it does not by itself prove every downstream
step completed. Email processing is intentionally recoverable:

```text
IMAP message
  -> hash delivery identity
  -> create/reuse email_ingestion_receipt
  -> canonical protected ingestion
  -> persist tokenized_content
  -> recover and route protected sender endpoint
  -> create customer_record_link
  -> correlate reply reference when available
  -> refresh customer attention
```

Existing receipts must be reconciled, not blindly skipped. This is why `sync_mailbox()` retries a
bounded set of `ready`/`protected` receipts whose `customer_id` is still null. Removing that retry
would recreate the failure where a reply is visible in `tokenized_content` but absent from the
customer timeline.

### Conversations and citations

| Table | Responsibility |
|---|---|
| `conversations` | User-owned, tenant-scoped conversation and optional active customer context |
| `conversation_turns` | Protected user/assistant turns, sequence, mode, and expiry |
| `conversation_turn_citations` | Exact protected sources used by a turn |

Conversation ownership and tenant RLS must remain intact. `context_customer_id` is the durable
customer scope for follow-up questions; it is not inferred solely from the most recent wording.

### Customers and identity

| Table | Responsibility |
|---|---|
| `customers` | Canonical tenant customer, provisional/confirmed state, identity-review state, and protected primary-name token |
| `customer_aliases` | Protected cross-source aliases with confidence and review status |
| `customer_record_links` | Evidence link from one customer to one protected content row |
| `customer_endpoints` | Unique tenant-owned protected email/Telegram endpoint and verification state |
| `customer_identity_claims` | Reviewable display-name or self-identification claims supported by protected content |
| `customer_attention_snapshots` | Immutable calculated attention result for an input fingerprint |
| `customer_attention_signals` | Evidence-backed components contributing to an attention snapshot |

An email endpoint is unique by `(tenant_id, channel, endpoint_token)`, so the same protected email
address cannot silently belong to two customers in one tenant. New inbound senders may create a
provisional profile. A changed name from the same endpoint creates reviewable identity evidence; it
must not silently reassign the endpoint or overwrite an accepted identity.

The customer page's linked-source count is the number of distinct
`customer_record_links.tokenized_content_id` values. It is **not** the number of email receipts,
identity claims, reply correlations, or outreach actions.

### Governed actions and business intelligence

| Tables | Responsibility |
|---|---|
| `outreach_actions`, `outreach_evidence` | Protected email draft, evidence lineage, approval, idempotent send state, provider reference, and reply state |
| `process_recommendations`, `recommendation_evidence`, `recommendation_decisions` | Evidence-backed process recommendation, source lineage, and approval decision |
| `einvoice_records`, `einvoice_outreach_drafts` | Structured e-Invoice readiness/payment data and legacy invoice outreach drafts |

Governed email follows the state machine:

```text
draft -> pending_approval -> approved -> sending -> sent -> replied
   |            |               |          |
cancelled    rejected         failed   delivery_unknown
```

Do not send directly from a route or mark an action `sent` before SMTP succeeds. The sender worker
claims approved work idempotently, stores only a hash of the provider message reference, and uses
that hash plus the protected sender endpoint for reply correlation.

### Audit

- `audit_log` records protected disclosure activity.
- `workflow_audit_log` records workflow and state-change activity.
- Both logs are hash-chained and protected by append-only triggers that reject update and delete.
- They are tamper-evident within the database, not an externally anchored immutable ledger.

Never update or delete audit rows, recompute old hashes casually, or add an application path that
bypasses the existing audit writers.

## Database change rules

Every contributor must follow all of these rules:

1. **Never edit an already-applied migration.** Add the next timestamped migration.
2. **Never make schema changes only in the Supabase Dashboard.** The migration must be committed.
3. **Keep migration, SQLAlchemy model, and schema checker synchronized in one change.**
4. **Prefer additive, backfilled migrations.** Add nullable, backfill deterministically, then add
   `NOT NULL`, foreign keys, uniqueness, indexes, grants, and RLS.
5. **Preserve tenant identity on parent and child tables.** New business tables require
   `tenant_id`, an FK to `tenants`, a tenant-leading index, and tenant-aware RLS.
6. **Use restrictive foreign-key deletion behavior for protected evidence.** Do not cascade-delete
   source content, vault entries, customer evidence, or audit history merely to simplify cleanup.
7. **Do not store raw PII in new columns or JSON.** Route text and metadata through the protection
   layer; store a protected token, ciphertext, masked value, safe classification, or opaque hash.
8. **Do not weaken RLS to fix application code.** Requests use `finbrain_app`; workers use
   `finbrain_worker`; both require correct transaction context.
9. **Do not treat a durable receipt as completion.** Multi-stage workers must be idempotent and
   retry post-persistence processing.
10. **Do not reseed or reset the shared Supabase project for ordinary development.** Use a separate
    test/staging project or SQLite tests. A reset destroys ingested records, customer profiles,
    conversations, decisions, correlation state, rotation history, and audit history.
11. **Do not run vault rotation while changing vault schema or secrets.** Confirm the active key,
    referenced key versions, and job state first. Keep `TOKEN_ROOT_SECRET` stable across deploys.
12. **Do not expose direct table access to the browser.** Add or update a FastAPI operation that
    applies authentication, RLS context, privacy protection, and audit behavior.

## Required validation before merge

From the repository root, with the FinBrain environment activated:

```powershell
cd backend
uv run --active --no-sync python -m pytest
uv run --active --no-sync ruff check .
uv run --active --no-sync python -m scripts.check_supabase
cd ..
npx.cmd supabase migration list
git diff --check
```

For a migration, first push to a separate Supabase test/staging project and run
`scripts.check_supabase` against it. Review the exact migration list before approving
`npx.cmd supabase db push`. The CLI warning about failing to cache the pg-delta catalog because
Docker is absent can appear after a successful remote push; the authoritative checks are the
reported applied migrations, `supabase migration list`, and `scripts.check_supabase`.

Before merging, the reviewer should be able to answer yes to all of the following:

- Does every new protected/business table have tenant scoping and forced RLS?
- Are grants limited to `finbrain_app` or `finbrain_worker` as appropriate?
- Does any new user-visible value originate from raw PII outside the authorized disclosure path?
- Are connector and outbound operations idempotent across crashes after any commit?
- Are state transitions and evidence links represented explicitly rather than inferred from row
  existence?
- Can the migration run on an existing populated database without dropping data?
- Do the models and `check_supabase.py` describe the final schema?
- Do focused tests cover retry, duplicate, tenant, authorization, and failure behavior?

## Emergency rule

If Supabase and the code disagree, stop workers that mutate the affected tables, preserve the
database, and inspect migration history and live schema read-only. Do not reset, delete rows, rotate
keys, loosen RLS, or force a migration version until the mismatch is understood. Repair forward
with a new migration and an idempotent reconciliation/backfill where necessary.
