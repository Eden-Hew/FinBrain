# Telegram Customer Onboarding and Overdue Reminder Design Specification

**Date:** 2026-08-21  
**Status:** Proposed  
**Target:** Customer-facing Telegram onboarding, endpoint reconciliation, invoice matching, and governed overdue reminders

---

## 1. Goal

Allow a customer who starts a private conversation with the FinBrain Telegram bot to:

1. establish a persistent Telegram identity;
2. submit a name, Gmail address, and phone number in a guided sequence;
3. create or reconcile a provisional FinBrain customer profile without storing raw PII outside the vault;
4. link e-Invoices to that customer using protected endpoint tokens; and
5. receive idempotent Telegram reminders for validated, unpaid, overdue invoices.

This extends the current operator-only capture bot. Operator capture and customer onboarding remain separate modes with separate authorization rules.

## 2. Supabase Contract

This design follows `SUPABASE_ARCHITECTURE.md` and `SUPABASE_SCHEMA_REFERENCE.md`:

- timestamped migrations are authoritative and already-applied migrations are never edited;
- every new business table is tenant-scoped, references `tenants`, has a tenant-leading index, forced RLS, and no `anon`/`authenticated` table grants;
- application and worker traffic use `finbrain_app` and `finbrain_worker`, neither with `BYPASSRLS`;
- raw Telegram IDs, usernames, email addresses, phone numbers, and message bodies are not stored in ordinary columns or JSON;
- deterministic tenant-scoped tokens support matching, while encrypted values remain in `token_vault`;
- durable receipts represent observed work, not completed work; reconciliation retries every post-persistence stage;
- reminder state transitions and workflow audit events are explicit and idempotent;
- browser clients do not gain direct table access.

## 3. Identity Model

### 3.1 Authoritative identifiers

| Value | Use | Persistence |
|---|---|---|
| Telegram `user.id` | Stable Telegram person/account endpoint | Tenant-scoped deterministic token plus vault ciphertext |
| Telegram private `chat.id` | Outbound delivery destination | Separate tenant-scoped token plus vault ciphertext |
| Telegram username | Optional mutable display evidence only | Protected token/vault entry; never used for ownership |
| Email address | Cross-source customer reconciliation and invoice matching | `EMAIL_*` endpoint token plus vault entry |
| Shared phone | Supporting endpoint; verified only when the Telegram contact belongs to the sender | `PHONE_*` endpoint token plus vault entry |

The username must never be a uniqueness or authorization key. A typed email is `observed`, not verified ownership. A Telegram endpoint is verified by direct private-chat interaction. A shared phone is verified only when `contact.user_id == update.effective_user.id`.

### 3.2 Customer reconciliation rules

Resolution is deterministic and tenant-scoped:

1. Resolve a verified Telegram endpoint if it already exists.
2. Otherwise resolve a unique, non-revoked email endpoint.
3. If the email belongs to an existing customer, attach the new Telegram endpoint but leave the email's existing verification state unchanged.
4. If no endpoint exists, create one provisional customer with `profile_origin = 'telegram'` and observed email endpoint.
5. If endpoint evidence points to different customers, create no merge, mark identity review required, and audit the conflict.

Typed email alone may create a provisional profile, but automated financial reminders require either a verified email/invoice link or an explicit signed invoice deep link.

## 4. Deep Modules and Seams

### 4.0 Guided onboarding and unified identity record

`/start` begins a guided collection flow. Onboarding values are not treated as three unrelated
business messages:

```text
/start
  -> show privacy notice and ask for name
  -> ask for Gmail address
  -> ask for phone number using Telegram contact sharing
  -> protect and unify the completed identity bundle
  -> resolve/create the customer and endpoints
  -> ask for the customer's first business message
```

Name, Gmail, phone, Telegram `user.id`, and Telegram private `chat.id` form one onboarding bundle.
After all required values pass validation, the adapter creates exactly one
`CanonicalIngestionRecord`:

```text
source_system = telegram
record_type = customer_onboarding_profile
tenant_id = configured customer-bot tenant
source_record_id = opaque tenant-scoped onboarding-session reference
text = protected source for the unified name/Gmail/phone identity evidence
```

The raw identity bundle exists only in trusted process memory while it is protected. The durable
onboarding session stores only protected tokens. The unified protected record is persisted in
`tokenized_content`, receives the normal protected summary and `vector(768)` embedding, and is
linked to the resolved customer using `match_basis = 'telegram_onboarding_profile'`.

Only after the profile is resolved does the bot ask for a business message. Every accepted
customer business message then becomes its own canonical record:

```text
source_system = telegram
record_type = customer_message
source_record_id = opaque tenant-scoped Telegram update/message reference
```

Each message is protected, persisted, linked to the already-resolved customer with
`match_basis = 'verified_telegram_endpoint'`, summarized, and embedded. `/start`, onboarding
prompts, and bot-authored replies are never added to general knowledge.

Profile creation depends on protected persistence and deterministic endpoint resolution, not on
external AI success. If summarization or embedding fails, the unified profile record, customer,
endpoints, and links remain durable while enrichment is retried from protected content.

### 4.1 Endpoint resolution module

New module: `backend/app/services/customer_endpoint_resolution.py`

```python
def resolve_customer_endpoint(
    db: Session,
    evidence: EndpointEvidence,
) -> EndpointResolutionResult:
    ...
```

The interface accepts already classified raw evidence inside the trusted process and hides protection, vault persistence, uniqueness handling, provisional profile creation, conflict handling, record linking, and workflow audit writes. Email and Telegram are adapters at this seam.

### 4.2 Telegram onboarding module

New module: `backend/app/integrations/telegram/onboarding.py`

```python
def begin_onboarding(db: Session, identity: TelegramIdentity) -> OnboardingResult: ...
def submit_email(db: Session, identity: TelegramIdentity, email: str) -> OnboardingResult: ...
def submit_contact(db: Session, identity: TelegramIdentity, contact: ContactInput) -> OnboardingResult: ...
def reconcile_onboarding(db: Session, session_id: int) -> OnboardingResult: ...
```

The module owns the state machine and durable reconciliation. Telegram handlers only translate updates into these inputs and render results.

`OnboardingResult` includes the unified profile's protected `tokenized_content_id`.
Reconciliation creates a `customer_record_links` row with
`match_basis = 'telegram_onboarding_profile'`. Duplicate updates reuse the same profile row and
link. After completion, the handler routes customer messages through the existing canonical
ingestion seam and links them by the verified Telegram endpoint.

### 4.3 Reminder planning module

New module: `backend/app/services/overdue_reminders.py`

```python
def plan_due_reminders(db: Session, tenant_id: str, as_of: date) -> ReminderPlanResult: ...
```

It selects eligible invoices, resolves verified Telegram delivery endpoints, creates governed outreach actions with deterministic idempotency keys, and records evidence. It never calls Telegram directly.

### 4.4 Outbound delivery seam

```python
class OutreachDeliveryAdapter(Protocol):
    def send(self, delivery: ProtectedDelivery) -> DeliveryResult: ...
```

Existing SMTP delivery and new Telegram delivery are the first two real adapters. A dispatcher claims an approved action, chooses the adapter from `outreach_actions.channel`, performs role-authorized detokenization inside the worker, and commits the result after provider success/failure.

## 5. Schema Changes

Add one forward migration after `202608200007_email_worker_attention_read.sql`.

### 5.1 Extend `customer_endpoints`

```text
delivery_token       text        NULL
last_interaction_at  timestamptz NULL
```

- `endpoint_token` remains the stable identity token.
- `delivery_token` identifies the encrypted delivery destination. For email it is backfilled to `endpoint_token`; for Telegram it represents `chat.id`.
- Add `(tenant_id, channel, verification_status)` and `(tenant_id, delivery_token)` indexes.
- Do not store raw Telegram IDs or usernames.

### 5.2 Add `telegram_onboarding_sessions`

```text
id                     bigint      PK, identity
tenant_id              uuid        NOT NULL, FK tenants(id)
telegram_endpoint_token text        NOT NULL
telegram_delivery_token text        NOT NULL
name_token             text        NULL
email_token            text        NULL
phone_token            text        NULL
customer_id            bigint      NULL, FK customers(id), ON DELETE RESTRICT
status                 text        NOT NULL
failure_code           text        NULL
consented_at           timestamptz NULL
completed_at           timestamptz NULL
created_at             timestamptz NOT NULL, default now()
updated_at             timestamptz NOT NULL, default now()
```

Constraints and indexes:

- unique active session per `(tenant_id, telegram_endpoint_token)`;
- status check: `awaiting_consent`, `awaiting_name`, `awaiting_gmail`, `awaiting_phone`,
  `reconciling`, `awaiting_message`, `completed`, `review_required`, `cancelled`, `failed`;
- tenant-leading status/updated index for recovery;
- foreign keys use restrictive deletion behavior.

`name_token`, `email_token`, and `phone_token` remain null only until their respective guided
steps complete. Entering `reconciling` requires all three. Gmail validation accepts a single
syntactically valid `@gmail.com` address after case-folding; no address is inferred from arbitrary
message content.

### 5.3 Extend `telegram_update_receipts`

```text
tenant_id              uuid   NULL initially, then NOT NULL after backfill
customer_id            bigint NULL, FK customers(id), ON DELETE RESTRICT
onboarding_session_id  bigint NULL, FK telegram_onboarding_sessions(id), ON DELETE RESTRICT
```

Backfill existing rows to the current default tenant before applying `NOT NULL`. Replace global worker policies with tenant-aware policies. Change update deduplication to tenant-aware uniqueness if multiple tenant bot installations may receive overlapping update IDs.

### 5.4 Extend `einvoice_records`

```text
buyer_email_token  text NULL
buyer_phone_token  text NULL
```

These are protected deterministic tokens, never raw addresses. Add tenant-leading lookup indexes. During invoice creation/extraction, protect buyer contact data and resolve `buyer_customer_id` through unique endpoints. Conflicts remain unresolved and audited.

### 5.5 Extend `outreach_actions`

```text
origin_type          text        NOT NULL, default 'manual'
origin_invoice_id    bigint      NULL, FK einvoice_records(id), ON DELETE RESTRICT
scheduled_for        timestamptz NULL
created_by_actor_ref text        NULL
```

Permit `created_by_user_id` to be nullable only when `created_by_actor_ref` is present, enforced by a check constraint. Add channel/origin/status checks and a tenant-leading worker queue index.

Automated reminder idempotency key:

```text
sha256(tenant_id | invoice_id | telegram_endpoint_id | reminder_stage | policy_version)
```

No separate reminder table is required: `outreach_actions` is the durable state machine and `outreach_evidence` retains evidence lineage.

### 5.6 Add `tenant_outreach_policies`

```text
tenant_id                uuid        PK/FK tenants(id)
telegram_reminders_enabled boolean    NOT NULL, default false
grace_days               integer     NOT NULL, default 1
repeat_interval_days     integer     NOT NULL, default 7
max_reminders            integer     NOT NULL, default 3
require_approval         boolean     NOT NULL, default true
policy_version           integer     NOT NULL, default 1
updated_by_user_id       uuid        NULL, FK auth.users(id)
updated_at               timestamptz NOT NULL, default now()
```

Automatic sending is disabled by default. Switching `require_approval` off is an owner-controlled, audited action. This prevents a deployment from unexpectedly messaging every overdue customer.

## 6. RLS and Grants

- `telegram_onboarding_sessions`: worker CRUD for the current tenant; application read for finance/owner/compliance; no browser roles.
- `tenant_outreach_policies`: application read for finance/owner/compliance, owner-only update; worker select for current tenant.
- `telegram_update_receipts`: worker access restricted to `tenant_id = finbrain_tenant_id()`; compliance read may be added only if operationally required.
- `customer_endpoints`, `einvoice_records`, and `outreach_actions`: update existing policies without weakening existing role checks, always adding tenant predicates.
- Grant only required columns/operations to `finbrain_app` and `finbrain_worker`.
- Enable and force RLS on both new tables; revoke `anon` and `authenticated` grants.

## 7. State Machines

### 7.1 Onboarding

```text
awaiting_consent
  -> awaiting_name
  -> awaiting_gmail
  -> awaiting_phone
  -> reconciling
  -> awaiting_message
  -> completed
       |-> review_required
       |-> failed -> reconciling (retry)
  -> cancelled
```

Each transition is persisted before the bot replies. A duplicate update reuses its receipt and returns the already-computed state.

### 7.2 Reminder delivery

Use the existing governed outreach states:

```text
draft -> pending_approval -> approved -> sending -> sent
   |            |               |          |
cancelled    rejected         failed   delivery_unknown
```

Policy-driven reminders may enter `approved` directly only when the tenant policy explicitly disables approval. SMTP/Telegram success must occur before setting `sent`.

## 8. Reminder Eligibility

An invoice is eligible when all are true:

- tenant policy enables Telegram reminders;
- `status = 'validated'`;
- `paid_at IS NULL`;
- `due_date < as_of - grace_days`;
- `buyer_customer_id` is present;
- customer is confirmed, or policy explicitly permits verified provisional profiles;
- identity review status is clear;
- a non-revoked verified Telegram endpoint with `delivery_token` exists;
- no matching idempotency key exists;
- the policy's maximum reminder count has not been reached.

Before delivery, re-read the invoice under worker RLS. Cancel the action if it is paid, no longer overdue, the endpoint is revoked, or identity review becomes required.

## 9. Message Privacy

Templates are deterministic and protected before persistence. Default content includes invoice number, due date, currency, outstanding amount, and a neutral payment request. It excludes bank account numbers, TINs, addresses, and unrelated customer evidence.

Example authorized delivery:

```text
Payment reminder: Invoice INV-123 is overdue. The outstanding amount is RM 950.00.
Please arrange payment or contact us if you need assistance.
```

The protected form, not plaintext, is stored in `outreach_actions`. Exact values are restored only inside the authorized sender worker and disclosure is audited.

## 10. Operational Model

- Configure `TELEGRAM_CUSTOMER_TENANT_ID` for a single-tenant bot deployment; never run customer onboarding with blank worker tenant context.
- A future multi-tenant deployment should use one bot installation per tenant or signed deep links that resolve an allowed tenant before setting worker context.
- Add `TELEGRAM_CUSTOMER_ONBOARDING_ENABLED`, `TELEGRAM_OUTBOUND_ENABLED`, reminder interval, batch size, and stale-send recovery settings.
- Add a reminder-worker heartbeat to `integration_status`.
- Recover `sending` actions after a lease timeout as `delivery_unknown` unless provider idempotency proves the result.

## 11. Out of Scope

- Telegram groups and channels;
- using username as an identity key;
- silently merging conflicting customers;
- collecting Gmail or phone without user action;
- payment processing inside Telegram;
- editing or deleting audit history;
- direct Supabase table access from Telegram or the browser.

## 12. Acceptance Criteria

- A private Telegram user sees the privacy notice, submits a name and one valid Gmail address, shares their own
  phone contact, and obtain one tenant-scoped customer profile.
- Name, Gmail, phone, Telegram user identity, and Telegram delivery identity are unified into
  exactly one `customer_onboarding_profile` record in `tokenized_content` and one resolved customer.
- After onboarding, the first and every subsequent customer business message is represented as a
  separate `customer_message` record, linked to that customer, and receives the normal protected
  summary and embedding when enrichment succeeds.
- An enrichment outage does not prevent the protected first message, customer profile, endpoint,
  or customer-record link from being committed and retried.
- Duplicate updates, bot restarts, and retries do not create duplicate customers, endpoints, sessions, or reminders.
- A Telegram user ID, chat ID, username, email, and phone never appear raw in ordinary database columns, safe metadata, logs, or audit payloads.
- Existing email-first profiles reconcile by protected email endpoint without reassignment conflicts.
- An eligible overdue invoice produces at most one action per reminder stage/policy version.
- Paying an invoice before dispatch cancels the reminder.
- Telegram delivery uses the verified endpoint associated with `buyer_customer_id`.
- All new tables and policies pass the Supabase schema contract and live RLS tests.
