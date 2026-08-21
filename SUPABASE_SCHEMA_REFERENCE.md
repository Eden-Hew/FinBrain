# FinBrain Supabase Schema Reference

This is a human-readable disaster-recovery snapshot of the FinBrain `public` schema. It was read
from the live Supabase PostgreSQL catalog on **21 August 2026**, with repository commit `5d6fbc2` as
the known-good code and migration baseline.

This file records all 34 application tables and every live column. It complements
`SUPABASE_ARCHITECTURE.md`, which documents RLS, roles, privacy boundaries, worker invariants, and
safe change rules.

## Important recovery limitation

This Markdown file is a layout reference, not an executable backup. Recreating only these columns
would omit foreign keys, check constraints, unique constraints, indexes, sequences, pgvector,
grants, forced RLS policies, Auth hooks, functions, and append-only triggers.

The authoritative loss-tolerant reconstruction is:

1. Preserve the damaged project and stop its mutating workers. Do not experiment on the only copy.
2. Create a fresh Supabase project or recovery branch/project.
3. Use the complete `supabase/migrations` directory from the known-good Git baseline.
4. Apply migrations in filename order with `npx.cmd supabase db push`.
5. Re-enable the `public.custom_access_token_hook` in Supabase Auth.
6. Recreate Auth users and their `user_roles` rows if Auth data was also lost.
7. Point a temporary backend environment at the rebuilt project and run:

   ```powershell
   cd backend
   uv run --active --no-sync python -m scripts.check_supabase
   ```

8. Only switch application traffic after the complete check passes.
9. Reseed synthetic demonstration records only after the schema and Auth roles are verified.

If the old encrypted data is being restored, the matching `TOKEN_ROOT_SECRET` and all referenced
`vault_key_versions` are required. A new secret cannot decrypt old vault ciphertext. If data loss is
accepted and the database is rebuilt empty, create a new root secret and seed new vault generations.

## Notation

- `PK` means primary key.
- `identity` means a PostgreSQL generated identity value even when the catalog reports no ordinary
  column default.
- `NULL` means optional; otherwise the column is `NOT NULL`.
- All tables are in the `public` schema.
- `tokenized_content.embedding` is specifically `vector(768)`.
- User UUID foreign keys without a `public` target reference `auth.users(id)`.

## Table columns

### `tenants`

```text
id          uuid        PK, default gen_random_uuid()
name        text        NOT NULL
slug        text        NOT NULL, UNIQUE
created_at  timestamptz NOT NULL, default now()
```

### `user_roles`

```text
user_id     uuid        NOT NULL, PK part, FK auth.users(id)
user_role   text        NOT NULL
active      boolean     NOT NULL, default true
created_at  timestamptz NOT NULL, default now()
updated_at  timestamptz NOT NULL, default now()
tenant_id   uuid        NOT NULL, PK part, FK tenants(id)
```

Primary key: `(user_id, tenant_id)`.

### `tokenized_content`

```text
id                   bigint      PK, identity
source_record_id     text        NOT NULL, UNIQUE
content_text         text        NOT NULL
embedding            vector(768) NULL
record_type          text        NULL
summary              text        NULL
created_at           timestamptz NOT NULL, default now()
source_system        text        NOT NULL, default 'legacy'
occurred_at          timestamptz NULL
content_fingerprint  text        NULL
safe_metadata        jsonb       NOT NULL, default {}
structured_summary   jsonb       NULL
processing_status    text        NOT NULL, default 'protected'
processing_error     text        NULL
enrichment_mode      text        NULL
updated_at           timestamptz NOT NULL, default now()
tenant_id            uuid        NOT NULL, FK tenants(id)
```

### `protected_token_registry`

```text
token         text        PK
entity_type   text        NOT NULL
masked_value  text        NOT NULL
created_at    timestamptz NOT NULL, default now()
tenant_id     uuid        NOT NULL, FK tenants(id)
```

### `token_vault`

```text
token                 text        PK
entity_type           text        NOT NULL
encrypted_value       bytea       NOT NULL
nonce                 bytea       NOT NULL
allowed_roles         jsonb       NOT NULL
sensitivity           text        NOT NULL, default 'high'
source_record_id      text        NOT NULL
created_at            timestamptz NOT NULL, default now()
key_version           integer     NOT NULL, default 1
masked_value          text        NOT NULL, default '[restricted]'
encryption_algorithm  text        NOT NULL, default 'AES-256-GCM'
tenant_id             uuid        NOT NULL, FK tenants(id)
```

### `vault_key_versions`

```text
version       integer     PK
wrapped_key   bytea       NOT NULL
wrap_nonce    bytea       NOT NULL
status        text        NOT NULL
created_at    timestamptz NOT NULL, default now()
activated_at  timestamptz NULL
retired_at    timestamptz NULL
```

### `vault_rotation_jobs`

```text
id             bigint      PK, identity
from_version   integer     NOT NULL, FK vault_key_versions(version)
to_version     integer     NOT NULL, FK vault_key_versions(version)
status         text        NOT NULL
rows_total     integer     NOT NULL
rows_rotated   integer     NOT NULL, default 0
last_token     text        NULL
failure_code   text        NULL
started_at     timestamptz NOT NULL, default now()
completed_at   timestamptz NULL
```

### `audit_log`

```text
id          bigint      PK, identity
prev_hash   text        NOT NULL
event_hash  text        NOT NULL
user_role   text        NOT NULL
token       text        NOT NULL
authorized  boolean     NOT NULL
query_hash  text        NOT NULL
ts          timestamptz NOT NULL, default now()
actor_ref   text        NOT NULL, default 'legacy'
tenant_id   uuid        NULL, FK tenants(id)
```

This table is append-only through a database trigger.

### `workflow_audit_log`

```text
id             bigint      PK, identity
prev_hash      text        NOT NULL
event_hash     text        NOT NULL
event_type     text        NOT NULL
actor_role     text        NOT NULL
actor_ref      text        NOT NULL
resource_type  text        NOT NULL
resource_id    text        NOT NULL
event_payload  jsonb       NOT NULL
created_at     timestamptz NOT NULL, default now()
tenant_id      uuid        NULL, FK tenants(id)
```

This table is append-only through a database trigger.

### `telegram_update_receipts`

```text
update_id         bigint      PK
tenant_id         uuid        NOT NULL, FK tenants(id)
message_ref_hash  text        NULL, UNIQUE
actor_ref         text        NOT NULL
source_record_id  text        NULL
update_kind       text        NOT NULL
status            text        NOT NULL, default 'received'
failure_code      text        NULL
customer_id       bigint      NULL, FK customers(id), ON DELETE RESTRICT
onboarding_session_id bigint  NULL, FK telegram_onboarding_sessions(id), ON DELETE RESTRICT
created_at        timestamptz NOT NULL, default now()
updated_at        timestamptz NOT NULL, default now()
```

### `telegram_onboarding_sessions`

```text
id                       bigint      PK, identity
tenant_id                uuid        NOT NULL, FK tenants(id)
telegram_endpoint_token  text        NOT NULL
telegram_delivery_token  text        NOT NULL
name_token               text        NULL
email_token              text        NULL
phone_token              text        NULL
customer_id              bigint      NULL, FK customers(id), ON DELETE RESTRICT
profile_content_id       bigint      NULL, FK tokenized_content(id), ON DELETE RESTRICT
status                   text        NOT NULL, default 'awaiting_consent'
failure_code             text        NULL
consented_at             timestamptz NULL
completed_at             timestamptz NULL
created_at               timestamptz NOT NULL, default now()
updated_at               timestamptz NOT NULL, default now()
```

Unique key: `(tenant_id, telegram_endpoint_token)`.

### `tenant_outreach_policies`

```text
tenant_id                    uuid        PK, FK tenants(id)
telegram_reminders_enabled   boolean     NOT NULL, default false
grace_days                   integer     NOT NULL, default 1
repeat_interval_days         integer     NOT NULL, default 7
max_reminders                integer     NOT NULL, default 3
require_approval             boolean     NOT NULL, default true
policy_version               integer     NOT NULL, default 1
updated_by_user_id           uuid        NULL, FK auth.users(id)
updated_at                   timestamptz NOT NULL, default now()
```

### `integration_status`

```text
integration_key    text        PK
status             text        NOT NULL
mode               text        NOT NULL
detector_ready     boolean     NOT NULL, default false
last_heartbeat_at  timestamptz NOT NULL, default now()
last_update_at     timestamptz NULL
failure_code       text        NULL
started_at         timestamptz NULL
```

### `email_sync_state`

```text
connector_key  text        PK
mailbox_ref    text        NOT NULL
folder_name    text        NOT NULL
last_uid       bigint      NOT NULL, default 0
last_sync_at   timestamptz NULL
status         text        NOT NULL, default 'idle'
failure_code   text        NULL
created_at     timestamptz NOT NULL, default now()
updated_at     timestamptz NOT NULL, default now()
```

### `email_ingestion_receipts`

```text
message_ref_hash       text        PK
source_record_id       text        NULL, UNIQUE
status                 text        NOT NULL, default 'received'
failure_code           text        NULL
received_at            timestamptz NOT NULL, default now()
processed_at           timestamptz NULL
customer_id            bigint      NULL, FK customers(id)
outreach_action_id     text        NULL, FK outreach_actions(id)
in_reply_to_ref_hash   text        NULL
correlation_status     text        NULL
correlated_at          timestamptz NULL
```

### `email_reply_correlations`

```text
id                        bigint      PK, identity
tenant_id                 uuid        NOT NULL, FK tenants(id)
email_receipt_ref_hash    text        NOT NULL, FK email_ingestion_receipts(message_ref_hash)
outreach_action_id        text        NOT NULL, FK outreach_actions(id)
matched_reference_hash    text        NOT NULL
customer_id               bigint      NOT NULL, FK customers(id)
tokenized_content_id      bigint      NOT NULL, FK tokenized_content(id)
status                    text        NOT NULL, default 'correlated'
created_at                timestamptz NOT NULL, default now()
```

Unique key: `(email_receipt_ref_hash, outreach_action_id)`.

### `structured_ingestion_batches`

```text
batch_ref       text        PK
schema_name     text        NOT NULL
origin_channel  text        NOT NULL
status          text        NOT NULL
total_rows      integer     NOT NULL
valid_rows      integer     NOT NULL
failed_rows     integer     NOT NULL
protected_rows  integer     NOT NULL
ready_rows      integer     NOT NULL
failure_code    text        NULL
created_at      timestamptz NOT NULL, default now()
updated_at      timestamptz NOT NULL, default now()
```

### `conversations`

```text
id                   text        PK
status               text        NOT NULL, default 'active'
created_at           timestamptz NOT NULL, default now()
updated_at           timestamptz NOT NULL, default now()
expires_at           timestamptz NOT NULL
created_by_user_id   uuid        NULL, FK auth.users(id)
tenant_id            uuid        NOT NULL, FK tenants(id)
context_customer_id  bigint      NULL, FK customers(id), ON DELETE SET NULL
context_updated_at   timestamptz NULL
```

### `conversation_turns`

```text
id                     bigint      PK, identity
conversation_id        text        NOT NULL, FK conversations(id)
sequence_number        integer     NOT NULL
user_role              text        NOT NULL
protected_question     text        NOT NULL
protected_answer       text        NOT NULL
query_intent           text        NOT NULL
source_systems         jsonb       NOT NULL
reasoning_mode         text        NOT NULL
insufficient_evidence  boolean     NOT NULL
created_at             timestamptz NOT NULL, default now()
protected_brief        jsonb       NULL
tenant_id              uuid        NOT NULL, FK tenants(id)
```

Unique key: `(conversation_id, sequence_number)`.

### `conversation_turn_citations`

```text
id                    bigint  PK, identity
turn_id               bigint  NOT NULL, FK conversation_turns(id)
ordinal               integer NOT NULL
tokenized_content_id  bigint  NOT NULL, FK tokenized_content(id)
tenant_id             uuid    NOT NULL, FK tenants(id)
```

Unique keys: `(turn_id, ordinal)` and `(turn_id, tokenized_content_id)`.

### `process_recommendations`

```text
id                     bigint           PK, identity
fingerprint            text             NOT NULL, UNIQUE
title                  text             NOT NULL
problem_statement      text             NOT NULL
recommendation         text             NOT NULL
expected_benefit       text             NOT NULL
suggested_owner        text             NOT NULL
success_metric         text             NOT NULL
category               text             NOT NULL
priority               text             NOT NULL
confidence             double precision NOT NULL
status                 text             NOT NULL, default 'proposed'
analysis_window_start  timestamptz      NOT NULL
analysis_window_end    timestamptz      NOT NULL
record_count           integer          NOT NULL
source_systems         jsonb            NOT NULL
enrichment_mode        text             NOT NULL
created_at             timestamptz      NOT NULL, default now()
updated_at             timestamptz      NOT NULL, default now()
origin_type            text             NOT NULL, default 'process_analysis'
origin_turn_id         bigint           NULL, FK conversation_turns(id), ON DELETE SET NULL
origin_query_hash      text             NULL
created_by_user_id     uuid             NULL, FK auth.users(id)
tenant_id              uuid             NOT NULL, FK tenants(id)
```

### `recommendation_evidence`

```text
id                    bigint      PK, identity
recommendation_id     bigint      NOT NULL, FK process_recommendations(id), ON DELETE CASCADE
tokenized_content_id  bigint      NOT NULL, FK tokenized_content(id), ON DELETE RESTRICT
evidence_excerpt      text        NOT NULL
relevance_reason      text        NOT NULL
created_at            timestamptz NOT NULL, default now()
tenant_id             uuid        NOT NULL, FK tenants(id)
```

Unique key: `(recommendation_id, tokenized_content_id)`.

### `recommendation_decisions`

```text
id                   bigint      PK, identity
recommendation_id    bigint      NOT NULL, FK process_recommendations(id), ON DELETE CASCADE
decision             text        NOT NULL
actor_role           text        NOT NULL
actor_ref            text        NOT NULL
protected_comment    text        NULL
created_at           timestamptz NOT NULL, default now()
tenant_id            uuid        NOT NULL, FK tenants(id)
```

### `customers`

```text
id                      bigint      PK, identity
tenant_id               uuid        NOT NULL, FK tenants(id)
canonical_name          text        NOT NULL
normalized_name         text        NOT NULL
created_at              timestamptz NOT NULL, default now()
profile_status          text        NOT NULL, default 'confirmed'
identity_review_status  text        NOT NULL, default 'clear'
profile_origin          text        NOT NULL, default 'manual'
primary_name_token      text        NULL
```

Unique key: `(tenant_id, normalized_name)`.

### `customer_aliases`

```text
id                   bigint           PK, identity
tenant_id            uuid             NOT NULL, FK tenants(id)
customer_id          bigint           NOT NULL, FK customers(id), ON DELETE RESTRICT
alias_token          text             NOT NULL
alias_type           text             NOT NULL
match_status         text             NOT NULL
confidence           double precision NOT NULL
source_system        text             NOT NULL
source_record_id     text             NULL
created_by_user_id   uuid             NULL
reviewed_by_user_id  uuid             NULL
created_at           timestamptz      NOT NULL, default now()
reviewed_at          timestamptz      NULL
```

Unique key: `(tenant_id, customer_id, alias_token)`.

### `customer_record_links`

```text
id                    bigint           PK, identity
tenant_id             uuid             NOT NULL, FK tenants(id)
customer_id           bigint           NOT NULL, FK customers(id), ON DELETE RESTRICT
tokenized_content_id  bigint           NOT NULL, FK tokenized_content(id), ON DELETE RESTRICT
alias_id              bigint           NULL, FK customer_aliases(id), ON DELETE RESTRICT
match_status          text             NOT NULL
confidence            double precision NOT NULL
match_basis           text             NOT NULL
created_by_user_id    uuid             NULL
reviewed_by_user_id   uuid             NULL
created_at            timestamptz      NOT NULL, default now()
reviewed_at           timestamptz      NULL
```

Unique key: `(tenant_id, customer_id, tokenized_content_id, match_basis)`.

### `customer_endpoints`

```text
id                    bigint      PK, identity
tenant_id             uuid        NOT NULL, FK tenants(id)
customer_id           bigint      NOT NULL, FK customers(id), ON DELETE RESTRICT
channel               text        NOT NULL
endpoint_token        text        NOT NULL
delivery_token        text        NULL
verification_status   text        NOT NULL
verified_by_user_id   uuid        NULL
verified_at           timestamptz NULL
last_interaction_at   timestamptz NULL
created_at            timestamptz NOT NULL, default now()
origin                text        NOT NULL, default 'manual'
```

Unique key: `(tenant_id, channel, endpoint_token)`. Endpoint ownership must remain unique within a
tenant regardless of customer.

### `customer_identity_claims`

```text
id                    bigint           PK, identity
tenant_id             uuid             NOT NULL, FK tenants(id)
customer_id           bigint           NOT NULL, FK customers(id), ON DELETE RESTRICT
endpoint_id           bigint           NOT NULL, FK customer_endpoints(id), ON DELETE RESTRICT
identity_token        text             NOT NULL
claim_basis           text             NOT NULL
confidence            double precision NOT NULL
evidence_content_id   bigint           NOT NULL, FK tokenized_content(id), ON DELETE RESTRICT
status                text             NOT NULL, default 'observed'
occurrence_count      integer          NOT NULL, default 1
first_seen_at         timestamptz      NOT NULL, default now()
last_seen_at          timestamptz      NOT NULL, default now()
reviewed_by_user_id   uuid             NULL
reviewed_at           timestamptz      NULL
```

Unique key: `(tenant_id, customer_id, endpoint_id, identity_token, claim_basis)`.

### `customer_attention_snapshots`

```text
id                   bigint      PK, identity
tenant_id            uuid        NOT NULL, FK tenants(id)
customer_id          bigint      NOT NULL, FK customers(id), ON DELETE RESTRICT
score                integer     NOT NULL
priority             text        NOT NULL
calculation_version  text        NOT NULL
input_fingerprint    text        NOT NULL
calculated_at        timestamptz NOT NULL, default now()
```

Unique key: `(tenant_id, customer_id, input_fingerprint)`.

### `customer_attention_signals`

```text
id                    bigint           PK, identity
tenant_id             uuid             NOT NULL, FK tenants(id)
snapshot_id           bigint           NOT NULL, FK customer_attention_snapshots(id), ON DELETE CASCADE
signal_type           text             NOT NULL
points                integer          NOT NULL
label                 text             NOT NULL
freshness             text             NOT NULL
confidence            double precision NOT NULL
tokenized_content_id  bigint           NULL, FK tokenized_content(id), ON DELETE RESTRICT
einvoice_record_id    bigint           NULL, FK einvoice_records(id), ON DELETE RESTRICT
occurred_at           timestamptz      NULL
details               jsonb            NOT NULL, default {}
```

At least one of `tokenized_content_id` or `einvoice_record_id` must be non-null.

### `outreach_actions`

```text
id                         text        PK
tenant_id                  uuid        NOT NULL, FK tenants(id)
customer_id                bigint      NOT NULL, FK customers(id)
customer_endpoint_id       bigint      NOT NULL, FK customer_endpoints(id)
channel                    text        NOT NULL
protected_subject          text        NOT NULL
protected_body             text        NOT NULL
status                     text        NOT NULL
idempotency_key            text        NOT NULL
created_by_user_id         uuid        NULL
created_by_actor_ref       text        NULL
origin_type                text        NOT NULL, default 'manual'
origin_invoice_id          bigint      NULL, FK einvoice_records(id), ON DELETE RESTRICT
scheduled_for              timestamptz NULL
approved_by_user_id        uuid        NULL
approved_at                timestamptz NULL
send_started_at            timestamptz NULL
sent_at                    timestamptz NULL
replied_at                 timestamptz NULL
provider_message_ref_hash  text        NULL
failure_code               text        NULL
attempt_count              integer     NOT NULL, default 0
created_at                 timestamptz NOT NULL, default now()
updated_at                 timestamptz NOT NULL, default now()
```

Unique keys: `(tenant_id, idempotency_key)` and `(tenant_id, provider_message_ref_hash)`.

### `outreach_evidence`

```text
id                    bigint  PK, identity
tenant_id             uuid    NOT NULL, FK tenants(id)
outreach_action_id    text    NOT NULL, FK outreach_actions(id), ON DELETE CASCADE
tokenized_content_id  bigint  NOT NULL, FK tokenized_content(id), ON DELETE RESTRICT
purpose               text    NOT NULL, default 'supporting'
```

Unique key: `(outreach_action_id, tokenized_content_id)`.

### `einvoice_records`

```text
id                     bigint         PK, identity
supplier_name          text           NOT NULL
supplier_tin           text           NULL
buyer_name             text           NULL
invoice_no             text           NULL
issue_date             date           NULL
currency               text           NULL
tax_type               text           NULL
tax_rate               text           NULL
total_amount           numeric(12,2)  NOT NULL
status                 text           NOT NULL, default 'pending'
source_record_id       text           NULL
created_at             timestamptz    NOT NULL, default now()
updated_at             timestamptz    NOT NULL, default now()
document_storage_path  text           NULL
uin                    text           NULL
tenant_id              uuid           NOT NULL, FK tenants(id)
buyer_customer_id      bigint         NULL, FK customers(id)
buyer_email_token      text           NULL
buyer_phone_token      text           NULL
due_date               date           NULL
paid_at                date           NULL
```

### `einvoice_outreach_drafts`

```text
id                    bigint      PK, identity
einvoice_record_id    bigint      NOT NULL, FK einvoice_records(id), ON DELETE CASCADE
channel               text        NOT NULL
draft_text            text        NOT NULL
status                text        NOT NULL, default 'draft'
created_by_user_id    uuid        NULL
decided_by_user_id    uuid        NULL
created_at            timestamptz NOT NULL, default now()
decided_at            timestamptz NULL
tenant_id             uuid        NOT NULL, FK tenants(id)
```

## Critical non-column objects

The migration history must also restore these objects:

- Extensions: `vector`/pgvector and the cryptographic UUID support used by migrations.
- Database roles: `finbrain_app` and `finbrain_worker`, both without `BYPASSRLS`.
- Context functions: `finbrain_role()`, `finbrain_user_id()`, `finbrain_tenant_id()`, and
  `finbrain_actor_ref()`.
- Auth hook: `custom_access_token_hook(jsonb)`.
- Timestamp and audit functions, including `set_updated_at()`, `finbrain_audit_tail(text)`, and the
  audit mutation rejection function.
- Append-only triggers on `audit_log` and `workflow_audit_log`.
- Forced RLS and the table-specific policies for application and worker roles.
- HNSW vector index `tokenized_content_embedding_idx` using 768-dimensional embeddings.
- Tenant-leading, status, lookup, queue, expiry, source, citation, and audit indexes defined by the
  migrations.

## Drift check

After any database pull or migration, compare the live database against this reference and run the
automated contract:

```powershell
cd backend
uv run --active --no-sync python -m scripts.check_supabase
```

If a future intentional migration changes any table above, update this file in the same commit as
the migration, SQLAlchemy model, and `check_supabase.py`. If the change is not intentional, do not
edit this reference to make the mismatch disappear; repair the database forward from the
known-good migration history.
