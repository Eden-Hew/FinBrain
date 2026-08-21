# Multichannel Customer Response: Email and Telegram Implementation Plan

**Goal:** Extend the governed response composer shown after **Ask about this customer** so an operator can generate, approve, and deliver a response by either verified email or the customer's verified Telegram chat without exposing a Telegram user/chat ID as the recipient.

**Architecture:** Keep FastAPI as the trusted boundary and reuse `customer_endpoints`, `outreach_actions`, `outreach_evidence`, the protected vault, and the existing email and Telegram sender workers. The browser selects an existing endpoint ID; it never supplies a raw email address, Telegram user ID, or chat ID. The backend derives the channel from that endpoint, generates channel-appropriate protected content, and the matching worker decrypts the delivery destination only at send time.

**Supabase impact:** No schema migration is expected. The live schema already has `customer_endpoints.channel`, `endpoint_token`, `delivery_token`, and `outreach_actions.channel`. If implementation uncovers a missing database invariant, stop and create a separate forward-only migration plan rather than changing the schema opportunistically.

---

## Locked product behavior

1. Rename the collapsed action from **Draft email response** to **Respond to customer**.
2. Rename the card from **Governed email response** to **Governed customer response**.
3. Replace the email-only receiver control with a **Send via** dropdown.
4. Offer one option per deliverable endpoint:
   - `Telegram — {customer name}` for a verified Telegram endpoint with a delivery token.
   - `Email — {authorized email address}` for a verified email endpoint; use the masked address when the role cannot reveal it.
5. An observed but unverified email from Telegram onboarding is not deliverable. Do not silently promote it to verified. Surface a short `Email on file — verification required` note when it is the reason email is unavailable.
6. The selected Telegram destination is displayed as `To: {customer name} (Telegram)`. Never show the Telegram user ID or chat ID as recipient text.
7. The selected email destination is displayed as `To: {email address}` (or the authorized mask for roles without disclosure access).
8. Rename **Generate email draft** to **Generate response**.
9. Email responses keep a subject and body. Telegram responses expose only an editable message body; any non-null internal subject required by the existing table remains backend-owned and is not presented as a Telegram subject.
10. Approval remains separate from generation. Owner approval queues the action; it does not send directly from the HTTP request.
11. Rename channel-specific status text, for example:
    - `Approve and queue email` / `Approve and queue Telegram`
    - `Queued for the email worker` / `Queued for the Telegram worker`
    - `Email sent successfully` / `Telegram message sent successfully`
12. Telegram delivery must use the encrypted `customer_endpoints.delivery_token`, which resolves to the same private chat captured during onboarding.

---

## Security and data invariants

- A request may select only a `customer_endpoint_id` belonging to the same tenant and customer.
- The backend, not the browser, determines `outreach_actions.channel` from `CustomerEndpoint.channel`.
- Supported manual response channels are allow-listed to `email` and `telegram`.
- Both channels require a verified endpoint. Telegram additionally requires a non-null `delivery_token`.
- Raw Telegram identifiers must not appear in endpoint/action API responses, frontend state labels, logs, workflow audit payloads, or generated model context.
- `endpoint_token` remains the persistent Telegram-user identity used for reconciliation; `delivery_token` remains the protected same-chat destination used only by the worker.
- Protected evidence selection, role-authorized preview detokenization, owner-only approval, RLS context, and audit behavior remain unchanged.
- The response body is generated only from the selected customer's protected and linked evidence.
- Sending remains idempotent and state-driven: `draft -> pending_approval -> approved -> sending -> sent`, with the existing failure states.

---

## Target request and delivery flow

```text
Ask about this customer
  -> GET /customers/{id}/endpoints
  -> API returns safe display labels and delivery eligibility
  -> operator selects Email or Telegram endpoint
  -> POST /customers/{id}/outreach/generate with endpoint ID
  -> backend validates ownership/eligibility and derives channel
  -> model produces protected, channel-appropriate response
  -> operator edits and submits
  -> owner approves
  -> channel worker claims approved action
      email    -> decrypt endpoint token -> SMTP
      telegram -> decrypt delivery token -> Bot.send_message(chat_id=...)
  -> composer polls status and displays the channel-specific result
```

---

## Wave 1: End-to-end Telegram tracer

### Task 1: Add safe endpoint and action display contracts

**Files:**

- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routes/outreach.py`
- Modify: `frontend/src/api/client.ts`
- Test: `backend/tests/test_outreach.py`

**Implementation:**

- Add an additive `display_label` field to `CustomerEndpointResponse` and a `delivery_eligible` boolean so UI logic does not infer safety from raw endpoint values.
- Add an additive `recipient_label` field to `OutreachActionResponse`.
- For email, build the label from the role-authorized address or mask.
- For Telegram, build the label from the role-authorized accepted customer name and append `(Telegram)` only in the action recipient label. Fall back to `Customer (Telegram)` if the name is withheld.
- Stop detokenizing a Telegram `endpoint_token` into `authorized_value`; it is an internal identity key, not a human recipient address.
- Preserve `recipient` temporarily for compatibility, but do not populate it with Telegram identifiers. Mark frontend use of it as deprecated and prefer `recipient_label`.
- Compute Telegram eligibility as `verified && delivery_token != null`; compute email eligibility as `verified`.

**Tests and acceptance:**

- Owner endpoint/action responses contain `Aisha Rahman (Telegram)` and do not contain the raw Telegram user or chat ID.
- Finance responses fall back safely if the customer name is not authorized.
- Email labels retain the existing authorized/masked behavior.
- Cross-tenant and cross-customer endpoint access remains rejected.

### Task 2: Make outreach creation and generation channel-aware

**Files:**

- Modify: `backend/app/services/outreach.py`
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/test_outreach.py`

**Implementation:**

- Centralize endpoint validation in a helper returning the validated endpoint and derived channel.
- Change `create_action()` from hard-coded `channel="email"` to `channel=endpoint.channel` after allow-list and delivery-eligibility checks.
- Replace `verified_email_endpoint_required` with channel-neutral errors such as `verified_outreach_endpoint_required` and `telegram_delivery_destination_required`.
- Pass the derived channel into protected draft generation.
- Use channel-specific model instructions:
  - Email: professional email, subject plus body, existing configured signature behavior.
  - Telegram: concise chat response, no email subject language, no `reply to this email`, and no invented facts or contact details.
- Store a protected internal subject such as `Telegram response` to satisfy the existing non-null database column; omit it from the Telegram editor contract.
- Make draft updates channel-aware: email requires subject and body; Telegram requires body and preserves its internal subject.
- Include the real channel in workflow audit events without including destination values.

**Tests and acceptance:**

- Generating against a Telegram endpoint creates a `draft` action with `channel="telegram"` and protected evidence links.
- The Morpheus system prompt says Telegram/message rather than email and does not receive raw Telegram identifiers.
- Selecting an email endpoint preserves current behavior.
- A phone endpoint, unverified endpoint, Telegram endpoint without `delivery_token`, or endpoint owned by another customer/tenant is rejected.
- Idempotent retries return the original action and channel.

### Task 3: Deliver one manually approved Telegram response to the same chat

**Files:**

- Modify: `backend/app/services/outreach.py`
- Modify: `backend/app/integrations/telegram/sender.py` only if a focused eligibility/error adjustment is required
- Test: `backend/tests/test_outreach.py`
- Test: `backend/tests/test_telegram_sender.py`

**Implementation:**

- Make submit/approve validation channel-neutral while preserving confirmed-customer and clear-identity gates.
- Verify the existing Telegram sender accepts manual actions with `origin_type="manual"` and no invoice, decrypts only `delivery_token`, and sends only `protected_body` after authorized worker detokenization.
- Preserve the invoice revalidation branch only when `origin_invoice_id` exists.
- Keep provider acceptance, provider-reference hashing, retry/failure, and audit semantics unchanged.

**Tests and acceptance:**

- Full service test: generate Telegram response -> submit -> owner approve -> `dispatch_one()` -> exact onboarding chat ID receives the body -> action becomes `sent`.
- A changed/revoked endpoint before dispatch cancels delivery.
- A send failure does not mark the action sent and does not expose the chat ID.
- Existing overdue-reminder and email sender tests remain green.

Wave 1 is complete only when this tracer passes without any frontend work: the API can create, approve, and deliver a manual Telegram response safely.

---

## Wave 2: Composer UX and timely dispatch

### Task 4: Convert the Ask composer to multichannel UX

**Files:**

- Modify: `frontend/src/components/outreach/OutreachComposerCard.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/screens/Agents.tsx` only if the resolved customer name must be passed for a safe fallback

**Implementation:**

- Update TypeScript channel unions from email-only to `"email" | "telegram"`.
- Load all endpoints but make only `delivery_eligible` endpoints selectable.
- Render the `Send via` dropdown using server-provided safe labels.
- Do not render `authorized_value` for Telegram.
- Reset the draft when the operator changes endpoint/channel; never mutate the destination of an already-created action.
- Apply the locked copy changes above.
- Hide the subject input for Telegram and validate only its body; keep subject and body validation for email.
- Use `action.recipient_label` for `To:` and channel-specific approval, queued, sent, and failure copy.
- Keep status polling for both `approved` and `sending` states.
- If no deliverable endpoint exists, disable **Generate response** and explain whether verification or Telegram delivery setup is missing.
- Retain keyboard-accessible labels and status text; do not encode the channel only through color.

**Acceptance:**

- Customer with both verified channels sees both choices.
- Telegram-only customer sees a Telegram choice labeled with the customer name, never a number.
- Verified-email-only customer sees current email behavior with the revised generic wording.
- Changing the dropdown before generation changes the generated action channel.
- The screenshots' misleading numeric `Receiver` and email-only wording are gone.

### Task 5: Separate manual outbound dispatch cadence from reminder planning

**Files:**

- Modify: `backend/app/config.py`
- Modify: `backend/app/integrations/telegram/runner.py`
- Modify: environment/example configuration documentation used by the repository
- Test: add focused Telegram runner tests in the nearest existing Telegram test module

**Implementation:**

- Keep overdue reminder planning on `telegram_reminder_interval_seconds` (currently one hour).
- Add a short Telegram outbound polling interval, matching the responsive behavior expected after approval.
- Run a dedicated outbound loop that calls `dispatch_one()` for the configured batch size without creating reminders.
- Keep the reminder loop responsible only for `plan_due_reminders()`.
- Start both loops only when Telegram outbound is enabled, and preserve worker RLS tenant context and error isolation.
- Ensure concurrent loops cannot duplicate a send; rely on the transactional/locked claim and add a concurrency regression test where supported.

**Acceptance:**

- A manually approved Telegram response is picked up within the configured short interval rather than waiting up to one hour.
- Reminder planning cadence and idempotency remain unchanged.
- Worker heartbeat remains healthy when one loop encounters a recoverable exception.

---

## Wave 3: Regression, Supabase dry run, and UAT

### Task 6: Backend regression suite

Run from `backend`:

```powershell
uv run --active --no-sync python -m pytest tests/test_outreach.py tests/test_telegram_sender.py tests/test_overdue_reminders.py tests/test_email_sender.py
uv run --active --no-sync python -m pytest
uv run --active --no-sync ruff check .
```

Required assertions:

- No API response contains a raw Telegram user ID or chat ID.
- Email generation/sending and reply correlation remain unchanged.
- Telegram onboarding still creates one verified Telegram endpoint with its protected same-chat delivery token.
- Manual and overdue Telegram actions share the sender safely.
- Tenant, endpoint ownership, verification, customer-confirmation, and identity-review gates fail closed.

### Task 7: Frontend verification

Run from `frontend`:

```powershell
npm run lint
npm run build
```

Then perform browser UAT against seeded/test data:

1. Open a customer with both eligible endpoints and click **Ask about this customer**.
2. Generate an email response and verify subject/body, recipient address, submission, approval, and sent state.
3. Generate a Telegram response and verify body-only editing, `To: {name} (Telegram)`, submission, approval, and sent state.
4. Confirm the message arrives in the same private Telegram chat used for onboarding.
5. Inspect the browser network responses and application logs for absence of raw Telegram IDs.
6. Revoke the Telegram endpoint before approval/dispatch and verify delivery is blocked.

### Task 8: Supabase dry run and documentation verification

No `supabase db push` is expected because this plan requires no migration.

```powershell
cd backend
uv run --active --no-sync python -m scripts.check_supabase
cd ..
npx.cmd supabase migration list
git diff --check
```

- Confirm the live schema still matches `SUPABASE_SCHEMA_REFERENCE.md`.
- Confirm no modified file appears under `supabase/migrations/`.
- If any migration becomes necessary, test it first against a disposable Supabase project and update the migration, SQLAlchemy model, schema checker, architecture document, and schema reference in one atomic change.
- Update operator documentation with Telegram outbound enablement, the short dispatch interval, and the distinction between Telegram identity and delivery tokens.

---

## Definition of done

- The Ask composer offers every eligible email/Telegram method for the selected customer.
- Telegram is displayed as `To: {name} (Telegram)` and no user/chat ID reaches the UI.
- **Generate response** produces channel-appropriate editable content from protected evidence.
- The existing approval state machine governs both channels.
- An approved Telegram action is delivered promptly to the same onboarding chat through the Telegram worker.
- Email behavior and overdue-reminder behavior do not regress.
- Full backend tests/lint, frontend lint/build, read-only Supabase contract check, migration-list check, and browser UAT all pass.

## Explicitly out of scope

- Treating an observed onboarding Gmail address as verified without a verification workflow.
- Direct Telegram sending from a FastAPI route or browser request.
- Exposing Telegram usernames, user IDs, or chat IDs as destination labels.
- Adding Telegram reply-to-action correlation; inbound Telegram messages continue to be linked to the customer through the verified endpoint, but `outreach_actions.status="replied"` remains email-correlation behavior unless separately designed.
- Redesigning the separate manual outreach form on the Customer detail page beyond shared type/API compatibility.
