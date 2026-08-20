# FinBrain Customer Intelligence and Governed Email Outreach Guide

This guide explains how FinBrain turns protected cross-source customer evidence into a reviewed
email action. It covers the local demonstration flow, role boundaries, protected storage,
database verification, optional SMTP delivery, and exact reply correlation.

## 1. What this feature demonstrates

The feature connects five previously separate concerns into one controlled workflow:

1. Resolve a structured identity or create a provisional profile from a first-time Gmail sender
   without exposing that identity to an external model.
2. Link matching protected records from email, Telegram, e-invoices, and other ingested sources.
3. Calculate a deterministic attention score from verified evidence.
4. Let an authorized operator prepare an evidence-bound email without sending it immediately.
5. Require an owner to approve delivery and correlate a later reply through a hashed message
   reference.

The intended flow is:

```text
Structured customer record OR first inbound Gmail address
        |
        v
Verified protected aliases -----> matching protected source records
        |                                      |
        +----------------------+---------------+
                               v
                    Customer intelligence view
                               |
                               v
              Protected, evidence-bound email draft
                               |
                 finance submits for approval
                               |
                      owner approves delivery
                               |
                 SMTP worker sends when enabled
                               |
                 incoming reply is ingested first
                               |
        hashed In-Reply-To/References exact-match the action
                               |
                    action becomes `replied`
```

The external reasoning model receives protected tokens and evidence, not the original sensitive
values. Email addresses, draft PII, and correlated replies remain behind the same vault and
authorization boundary used by the rest of FinBrain.

## 2. Implemented components

### Customer identity

- `customers` stores the tenant-scoped canonical customer record.
- A previously unknown Gmail sender creates one `provisional` email-origin customer and one
  `observed` protected endpoint. Later messages from that address reuse the same profile; no
  invoice is required.
- `customer_aliases` stores deterministic protected aliases such as `ORG_...` and `PERSON_...`.
- `customer_identity_claims` stores protected display-name and explicit first-person claims with
  confidence, evidence, occurrence count, and owner review status.
- `customer_record_links` records which protected sources are linked to a customer and whether the
  match is verified, probable, ambiguous, or rejected.
- Gmail ingestion parses the RFC `From` address transiently and protects it as `sender_email`.
  One address can belong to only one customer within a tenant. The address, not a guessed name,
  establishes continuity.
- Morpheus receives only protected email text. It may propose a sender claim already present as a
  `PERSON_...` or `ORG_...` token, but strict backend validation and deterministic rules decide
  whether to record evidence. Model failure cannot prevent the provisional profile or ingestion.
- A later different name never overwrites the primary claim. It sets `review_required`, blocks
  outreach, and waits for an owner to accept it as primary/alias or reject it.
- Existing protected records can be linked after an alias becomes known by running the idempotent
  backfill script.

### Customer attention

- `customer_attention_snapshots` stores a versioned, deterministic score from 0 to 100.
- `customer_attention_signals` stores the evidence and points that produced the score.
- Scores do not depend on an LLM response and can be explained from stored evidence.

### Protected conversation context

- `conversations.context_customer_id` binds a conversation to a verified customer.
- Follow-up questions can refer to “this customer”, “their contact”, or “their issue” without
  reverting to a different customer from older conversation history.
- Retrieval remains tenant-scoped and evidence-based.

### Governed outreach

- `customer_endpoints` stores a protected email token and verification status—not a plaintext
  address.
- `outreach_actions` stores protected subject/body text and the action state.
- `outreach_evidence` binds each draft to the verified protected records used to justify it.
- `workflow_audit_log` records state transitions in the existing hash-chained workflow audit.

### Delivery and replies

- The existing email worker handles both inbound IMAP polling and optional outbound SMTP delivery.
- Outbound RFC `Message-ID` values are HMAC-hashed with tenant context before persistence.
- Incoming `In-Reply-To` and `References` headers are parsed transiently and immediately hashed.
- `email_reply_correlations` stores the exact protected correlation result.
- A unique exact reference plus the exact protected sender endpoint creates a verified
  customer-record link and changes the action to `replied`.
- A reference from a different address is stored as `identity_conflict`; the action stays sent.
- Reply correlation never changes invoice, payment, or refund state automatically.

## 3. Role and authorization matrix

| Capability | General employee | Finance operator | Compliance | Owner/director |
| --- | ---: | ---: | ---: | ---: |
| View customer intelligence | Yes | Yes | Yes | Yes |
| Use customer-scoped chat | Yes | Yes | Yes | Yes |
| Register a protected email endpoint | No | Yes | No | Yes |
| Verify an endpoint | No | No | No | Yes |
| Resolve protected identity claims | No | No | No | Yes |
| Create and submit a draft | No | Yes | No | Yes |
| Inspect pending governed outreach | No | Yes | Yes | Yes |
| Approve or reject delivery | No | No | No | Yes |
| View workflow audit | No | No | Yes | According to current audit policy |

Backend JWT authorization and PostgreSQL RLS both enforce these boundaries. Changing the persona
selector does not replace the authenticated user's JWT role.

## 4. Demonstration accounts

The configured Supabase demonstration accounts are:

| Role | Email |
| --- | --- |
| General employee | `employee@finbrain-demo.test` |
| Finance operator | `finance@finbrain-demo.test` |
| Compliance | `compliance@finbrain-demo.test` |
| Owner/director | `owner@finbrain-demo.test` |

For the current private demonstration environment, the shared password is:

```text
finbraindemo
```

Do not reuse this password for production or for any non-demonstration account.

## 5. Required environment configuration

For local customer-intelligence testing without real email delivery:

```dotenv
CUSTOMER_INTELLIGENCE_ENABLED=true
CUSTOMER_ATTENTION_ENABLED=true
EMAIL_REPLY_CORRELATION_ENABLED=true
OUTBOUND_EMAIL_ENABLED=false
```

Keep `OUTBOUND_EMAIL_ENABLED=false` during the first acceptance test. This proves that approval and
delivery are separate controls: an approved action must remain queued and no SMTP connection should
be attempted.

The database must include migrations `202608200001` through `202608200007`. Before pushing
`202608200006`, ensure no protected endpoint token is owned by multiple customers. The migration
also performs this preflight and aborts without partial application if duplicates exist. Verify
from `backend`:

```powershell
uv run --active --no-sync python -m scripts.check_supabase
```

Expected final lines include:

```text
Email-first customer identity, attention, governed outreach, and reply correlation: present
RLS: enabled and forced
Supabase database check passed.
```

## 6. Start the local application

From the repository root:

```powershell
& .\scripts\run_demo.ps1
```

Typical local addresses are:

```text
Frontend: http://127.0.0.1:5173
API docs: http://127.0.0.1:8000/docs
Status:   http://127.0.0.1:8000/status
```

If environment variables were changed while the application was running, stop and restart it:

```powershell
& .\scripts\stop_demo.ps1
& .\scripts\run_demo.ps1
```

## 7. Prepare one useful customer

The migration creates empty customer-intelligence tables; it does not reinterpret historical
records automatically. For a repeatable, non-destructive fixture, run from `backend`:

```powershell
uv run --active --no-sync python -m scripts.seed_demo_customer
```

The command is idempotent. It adds or reuses `Luma Retail Sdn Bhd`, invoice `LUMA-INV-3001`, a
protected customer email, verified evidence links, an attention snapshot, and an `observed`
protected endpoint. It does not reset or delete existing data.

Alternatively, the clearest manual test is to create one new e-invoice whose buyer name also
appears in existing protected evidence.

Log in as `finance@finbrain-demo.test` and create an e-invoice with values similar to:

```text
Supplier name: FinBrain Demo Supplier Sdn Bhd
Supplier TIN:  C1234567890
Buyer name:    Meranti Trading
Invoice no.:   CI-TEST-001
Issue date:    2026-08-20
Currency:      MYR
Tax type/rate: SST / 6%
Total amount:  RM 4,850
```

`Meranti Trading` is useful because the demonstration knowledge base already contains protected
records referring to that organization.

After creating the invoice, run from `backend`:

```powershell
uv run --active --no-sync python -m scripts.backfill_customer_links
uv run --active --no-sync python -m scripts.recalculate_customer_attention
```

The backfill is idempotent. It registers known protected aliases and scans existing protected
content for exact tenant-scoped token matches. The attention script creates a new snapshot only for
the current calculated input.

Refresh the Customers screen. The customer should display:

- attention score and priority;
- outstanding and overdue values;
- invoice count;
- verified linked-source count;
- an explanation for each attention signal;
- a protected cross-source timeline.

## 8. Acceptance test A: customer-scoped conversation

1. Open the new customer in Customers.
2. Select **Ask about this customer**.
3. Ask:

   ```text
   What needs attention for this customer, and why?
   ```

4. Follow with:

   ```text
   What contact information is available?
   ```

5. Continue with:

   ```text
   Suggest a concise response to their latest issue.
   ```

Expected behavior:

- the request carries the customer's numeric context ID;
- follow-ups remain about the same customer;
- returned claims cite only that customer's verified evidence;
- authorized values are restored according to the authenticated role;
- model view continues to show protected tokens.

## 9. Acceptance test B: protected endpoint registration

Log in as the finance operator and open the customer workspace.

Enter a demonstration address such as:

```text
demo.customer@example.com
```

Select **Protect endpoint**.

Expected behavior:

- the API accepts the raw address only at the trusted backend boundary;
- the finance UI subsequently displays a masked value;
- `customer_endpoints.endpoint_token` contains an `EMAIL_...` token;
- the plaintext address is stored only as encrypted vault material;
- the endpoint begins in `observed` state;
- finance cannot verify it.

Trying to submit outreach through an unverified endpoint must fail with:

```text
verified_email_endpoint_required
```

## 10. Acceptance test C: owner verification

1. Log out of the finance account.
2. Log in as `owner@finbrain-demo.test`.
3. Open the same customer.
4. Select **Verify endpoint**.

Expected behavior:

- the owner view displays the authorized original address and labels it as an authorized owner
  view;
- retrieving the original address uses the normal single-use disclosure flow and writes a
  disclosure audit event;
- status changes from `observed` to `verified`;
- `verified_by_user_id` and `verified_at` are recorded;
- a finance JWT still cannot perform the same update;
- PostgreSQL RLS permits the update only for `owner_director`.

## 11. Acceptance test D: evidence-bound drafting

Log in as finance again and prepare a message:

```text
Subject: Follow-up regarding CI-TEST-001

Hello,

We are following up regarding invoice CI-TEST-001. Our records indicate that it needs attention.
Please reply with an update when convenient.

Thank you.
```

Select **Submit for approval**.

The UI performs two governed operations:

```text
create protected draft -> submit draft for approval
```

Expected behavior:

- subject and body are tokenized before being stored in `outreach_actions`;
- the draft references only verified customer evidence;
- status progresses from `draft` to `pending_approval`;
- no SMTP delivery occurs;
- a repeated browser request with the same idempotency key would return the same action rather than
  creating another one.

The API refuses evidence that is missing, not ready, from another tenant, or not verified as linked
to the selected customer.

## 12. Acceptance test E: approval boundaries

### Finance

Finance can inspect the pending action but cannot approve or reject it. A direct API attempt should
return HTTP 403 with `owner_director_required`.

### Endpoint revocation

An owner/director can select **Revoke endpoint** for an observed or verified address. Revocation
preserves the protected endpoint, existing outreach references, and hash-chained audit history, but
immediately prevents new submission, approval, or delivery through that address. Re-entering the
same address is an explicit restore operation: the existing endpoint returns to `observed` and must
be verified again before it can be used. No plaintext address is duplicated in the database.

Verification also controls inbound identity linking. A new standalone Gmail message from a unique,
verified endpoint is linked to that customer using the protected sender token, even when the body
does not mention the person's or company's name. Observed, revoked, unknown, cross-tenant, or
multi-customer matches remain unlinked. Replies to governed outreach continue to use the stronger
exact `In-Reply-To`/`References` correlation first.

### Compliance

Log in as `compliance@finbrain-demo.test` and open Approvals:

- the pending protected action is visible;
- approval controls are disabled;
- compliance cannot change the action.

### Owner/director

Log in as the owner, open Approvals, find the Customer Intelligence outreach card, and select
**Approve & queue**.

Expected state:

```text
pending_approval -> approved
```

## 13. Acceptance test F: SMTP-disabled safety

With:

```dotenv
OUTBOUND_EMAIL_ENABLED=false
```

an approved action must behave as follows:

- remain in `approved` state;
- keep `attempt_count = 0`;
- have no `send_started_at` or `sent_at` timestamp;
- never enter `sending` or `sent`;
- produce no outbound email.

This is the expected result, not a worker failure. The email worker may continue inbound IMAP
polling while outbound dispatch remains disabled.

## 14. Outreach state machine

The supported human-controlled states are:

```text
draft -> pending_approval -> approved
  |             |
  v             v
cancelled     rejected
```

When SMTP is enabled, the worker-controlled states continue as:

```text
approved -> sending -> sent -> replied
                 |       
                 +-----> failed
                 +-----> delivery_unknown
```

Meaning of delivery results:

- `failed`: preparation, connection, authentication, or an explicit SMTP rejection failed before
  an uncertain delivery occurred.
- `delivery_unknown`: the worker entered the actual send operation but lost certainty about whether
  the provider accepted the message.
- `sent`: SMTP completed successfully.
- `replied`: a later protected inbound email contained an exact matching reply reference.

FinBrain does not automatically retry `failed` or `delivery_unknown` actions. This prevents a
timeout from sending a duplicate customer email.

## 15. Inspect the result in Supabase

Use Table Editor for a visual inspection, or SQL Editor for targeted checks.

### Customer identity and attention

```sql
select id, canonical_name, normalized_name, tenant_id
from public.customers
order by id;

select customer_id, alias_token, alias_type, match_status, confidence
from public.customer_aliases
order by customer_id, id;

select customer_id, tokenized_content_id, match_status, confidence, match_basis
from public.customer_record_links
order by customer_id, created_at;

select customer_id, score, priority, calculation_version, calculated_at
from public.customer_attention_snapshots
order by calculated_at desc;
```

### Protected endpoints and actions

```sql
select id, customer_id, channel, endpoint_token, verification_status, verified_at
from public.customer_endpoints
order by created_at desc;

select id, customer_id, status, protected_subject, protected_body,
       attempt_count, failure_code, approved_at, sent_at, replied_at
from public.outreach_actions
order by created_at desc;

select outreach_action_id, tokenized_content_id, purpose
from public.outreach_evidence
order by id;
```

The endpoint, subject, and body columns should contain protected values. Do not expect plaintext
email addresses or sensitive message fields in these tables.

### Workflow audit

```sql
select event_type, actor_role, resource_type, resource_id, created_at
from public.workflow_audit_log
where resource_type = 'outreach_action'
order by created_at desc;
```

Expected event types include:

```text
outreach_drafted
outreach_pending_approval
outreach_approved
outreach_sent
email_reply_correlated
```

Only events reached by the current test will be present.

## 16. Optional live SMTP test

Do this only with a controlled recipient that you own. Configure the backend environment:

```dotenv
OUTBOUND_EMAIL_ENABLED=true
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USERNAME=your-test-sender@gmail.com
EMAIL_SMTP_PASSWORD=your-gmail-app-password
EMAIL_SMTP_USE_STARTTLS=true
EMAIL_SMTP_FROM_ADDRESS=your-test-sender@gmail.com
```

Restart the application after changing the environment. Create a new action addressed to your
controlled inbox, submit it, and approve it once.

Expected progression:

```text
approved -> sending -> sent
```

Do not repeatedly approve or manually alter the state if delivery is slow. Check `/status`, the
email worker logs, and `outreach_actions` first.

## 17. Optional exact reply-correlation test

This test requires both successful outbound SMTP delivery and inbound IMAP ingestion.

1. Receive the FinBrain test email in the controlled inbox.
2. Use the mail provider's normal **Reply** action; do not compose an unrelated new message.
3. Send the reply back to the mailbox monitored by the FinBrain IMAP connector.
4. Wait for the email worker's next polling interval.

Expected behavior:

- the inbound email is protected through the normal ingestion pipeline first;
- raw `In-Reply-To` and `References` values are never persisted;
- their tenant-scoped HMAC hashes match `provider_message_ref_hash`;
- one row appears in `email_reply_correlations`;
- the receipt records `correlation_status = 'correlated'`;
- a verified `customer_record_links` row is created with `match_basis = 'exact_email_reply'`;
- the action becomes `replied` and receives `replied_at`;
- attention is recalculated when customer attention is enabled.

Verify with:

```sql
select status, customer_id, outreach_action_id, correlation_status, correlated_at
from public.email_ingestion_receipts
where outreach_action_id is not null
order by received_at desc;

select outreach_action_id, customer_id, tokenized_content_id,
       matched_reference_hash, status, created_at
from public.email_reply_correlations
order by created_at desc;
```

An unrelated email or a new message without the reply headers must not auto-link to the action.
Multiple possible matches are marked ambiguous and are not automatically linked.

## 18. API reference

The principal endpoints used by the frontend are:

```text
GET  /customers
GET  /customers/{customer_id}
GET  /customers/{customer_id}/timeline
GET  /customers/{customer_id}/endpoints
POST /customers/{customer_id}/endpoints
POST /customer-endpoints/{endpoint_id}/verify
POST /customers/{customer_id}/outreach
GET  /outreach
POST /outreach/{action_id}/submit
POST /outreach/{action_id}/approve
POST /outreach/{action_id}/reject
POST /outreach/{action_id}/cancel
POST /query
```

All calls require a valid Supabase access token. Backend authorization derives the tenant and role
from verified JWT claims; client-supplied role labels are not trusted.

## 19. Troubleshooting

### Customers screen is empty

The migration does not create customers from historical data. Create a new e-invoice with a buyer
name, then run:

```powershell
uv run --active --no-sync python -m scripts.backfill_customer_links
uv run --active --no-sync python -m scripts.recalculate_customer_attention
```

### Customer appears but has only one timeline record

- Confirm the buyer name exactly represents an organization already present in protected data.
- Run the link backfill after the alias exists.
- Inspect `customer_aliases` and `customer_record_links`.
- Probable or ambiguous identities are not treated as verified evidence automatically.

### Endpoint remains observed

Verification requires an authenticated owner/director JWT. Selecting the owner persona while still
logged in as finance does not grant owner authority.

### Draft cannot be submitted

Confirm:

- the endpoint is `verified`;
- every cited `tokenized_content_id` is ready;
- evidence is verified as linked to the same customer;
- the action is still in `draft` state.

### Approved action does not send

When `OUTBOUND_EMAIL_ENABLED=false`, this is correct. When it is true, verify all `EMAIL_SMTP_*`
values, restart the email worker, and inspect `/status` and worker logs.

### Action is delivery_unknown

Do not automatically resend. Confirm with the provider or recipient first. The status intentionally
represents a send whose final provider outcome is uncertain.

### Reply does not correlate

- Confirm the original action reached `sent` or `delivery_unknown`.
- Use Reply on the original message rather than composing a new email.
- Confirm `EMAIL_REPLY_CORRELATION_ENABLED=true` and restart the worker after changing it.
- Confirm the inbound message was ingested and has RFC reply headers.
- Check `email_ingestion_receipts.correlation_status`.

## 20. Verification commands

Run before a demonstration or deployment:

```powershell
cd backend
uv run --active --no-sync python -m scripts.check_supabase
uv run --active --no-sync python -m ruff check app tests seed scripts
uv run --active --no-sync python -m pytest

cd ..\frontend
npm.cmd run lint
npm.cmd run build
```

The implementation was last verified with 200 passing backend tests, clean Ruff output, no frontend
lint errors, a successful production frontend build, and all five customer/outreach migrations
applied with forced RLS.

## 21. Demonstration completion checklist

- [ ] Supabase schema check passes.
- [ ] Customer intelligence, attention, and reply-correlation flags are enabled.
- [ ] SMTP remains disabled for the non-delivery acceptance test.
- [ ] A customer exists and has verified aliases.
- [ ] Cross-source customer links are visible.
- [ ] Attention score explains its evidence.
- [ ] Customer-scoped chat maintains context across follow-ups.
- [ ] Finance can register but not verify an endpoint.
- [ ] Owner can verify the endpoint.
- [ ] Finance can draft and submit but cannot approve.
- [ ] Compliance can inspect but cannot approve.
- [ ] Owner can approve and queue the action.
- [ ] SMTP-disabled action remains approved with zero attempts.
- [ ] Protected database columns contain tokens rather than plaintext PII.
- [ ] Workflow audit contains the expected state transitions.
- [ ] Optional controlled SMTP delivery reaches `sent`.
- [ ] Optional reply through the original thread reaches `replied`.
