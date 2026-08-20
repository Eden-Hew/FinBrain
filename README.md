# FinBrain OS

FinBrain OS is a privacy-first customer-intelligence and process-optimization proof of concept for
Malaysian MSMEs. It unifies email, Telegram, uploaded documents, structured CSV rows, manual notes,
CRM-style records, bank exports, meetings, and support tickets behind one protected query and
workflow interface.

Raw inbound content crosses only the trusted FastAPI privacy boundary. Sensitive values are
detected, replaced with deterministic tenant-scoped tokens, and encrypted in a token vault before
external AI processing. Morpheus reasons over protected text, Gemini creates protected embeddings,
and FastAPI restores exact values only when the authenticated user's backend-owned role permits
disclosure.

FinBrain now supports the complete hackathon path:

```text
multi-source records
  -> protected ingestion
  -> SQL-first selection
  -> protected cited analysis
  -> role-authorized evidence inspection
  -> evidence-backed recommendation
  -> approval and implementation decision
  -> tamper-evident audit history
```

## What is implemented

- Unified, source-neutral protected ingestion through FastAPI.
- Manual ingestion workspace in the React frontend.
- Protected file preview and confirmed upload for TXT, Markdown, invoice CSV, EML, PDF, and DOCX.
- Strict `invoice_register_v1` CSV parsing with stable row identity and one citation per invoice.
- Private Telegram capture bot using local long polling.
- Read-only IMAP ingestion of new unread email and supported attachments.
- Email-first provisional customer profiles keyed by protected sender address, with protected
  self-identification claims and owner-reviewed conflict handling.
- Regex and optional GLiNER sensitive-data detection.
- Stable HMAC token identities separated from a versioned AES-256-GCM encrypted token vault.
- Random wrapped vault generations, per-token HKDF keys, authenticated row context, resumable
  rotation, and optional automatic rotation through a tracked worker.
- Query/actor/turn-bound in-memory disclosure sessions with single-use grants and safe
  format-shaped masks for unauthorized roles.
- Reversible, band-aware amount tokens with role-gated exact disclosure.
- Supabase Postgres, pgvector, HNSW indexing, forced RLS, non-bypass application/worker roles,
  database-enforced vault ACLs, and revoked Data API grants.
- Shared SQL-first counts, listings, date/type/category/action/metadata filters, and complete
  analytical record selection.
- Dedicated compact citation-card results for exact record listings, with lazy role-authorized
  evidence inspection and scroll-safe focus restoration.
- Protected six-turn conversation context with deterministic cited-record follow-ups.
- Protected Morpheus reasoning with validated `SOURCE-n` citations.
- Protected 20-record batching and final synthesis for larger analytical result sets.
- Structured Customer Intelligence Briefs with cited claims, timeline, missing information, and a
  governed recommended action.
- Lazy evidence inspection, an AI Exposure Receipt, and compliance-only role comparison over one
  stored protected result.
- Query-originated recommendations that retain their exact citation and query lineage through
  approval.
- Persistent process recommendations, evidence, approval decisions, and workflow audit events.
- Separate hash-chained disclosure and workflow audit logs with live verification, query
  references, previous hashes, and real entry hashes.
- Supabase email/password login with locally verified asymmetric JWTs and backend-owned roles.
- Four provisioned demonstration accounts matching the general employee, finance/operations,
  owner/director, and compliance roles.
- Twelve-record reset-safe demonstration dataset spanning six source systems.
- An unauthenticated `/status` service page reporting the backend and each configured worker
  (Telegram, email, vault rotation) with live status, uptime, started-at, and last-heartbeat times.

## Current architecture

```text
Telegram / unread IMAP / manual UI / protected file upload / seed adapters
                         |
                         v
              CanonicalIngestionRecord
                         |
                         v
              FastAPI privacy boundary
              Supabase JWT authorization
                 |               |
                 | detect PII    | raw input remains in memory only
                 | tokenize      |
                 | encrypt vault |
                 v               v
          protected content + protected metadata
                         |
             +-----------+-----------+
             |                       |
             v                       v
       Morpheus summary       Gemini embedding
             |                       |
             +-----------+-----------+
                         v
                 Supabase / SQLite
                         |
                         v
             shared SQL filter planner
             +-----------+-----------+
             |                       |
             v                       v
      exact count/list      all eligible protected records
                                     |
                                     v
                         Morpheus analysis and citations
                                     |
                                     v
                         role-gated detokenization
                                     |
                                     v
              role-authorized cited response
                                     |
                                     v
        recommendation / approval / audit workflow
```

The current proof-of-concept deliberately does not apply a top-five vector cap in `/query`.
Analytical questions use every ready record matching the trusted SQL source filter. If no source is
mentioned, every ready record across all source systems is eligible. Sets larger than 20 are
processed in protected batches before final synthesis. Stored embeddings and pgvector remain
available for a future scale-oriented retrieval policy.

## Prerequisites

- Windows PowerShell
- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Node.js and npm
- A Morpheus API key for protected reasoning
- A Gemini API key for 768-dimensional Supabase embeddings
- Optional: Supabase CLI, Telegram bot token, and Gmail app password

## 1. Install the project

From the repository root:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
Copy-Item backend\.env.example backend\.env

Set-Location backend
uv sync --extra dev

Set-Location ..\frontend
npm.cmd ci
Set-Location ..
```

For a conventional installation, `uv run` manages the backend environment automatically, so no
activation is required. The demo scripts also support workstation-specific Python environments:
they prefer `FINBRAIN_PYTHON` when set, then the root `.venv`, and use the uv-managed backend
environment only when neither direct Python option is available.

The standard installation includes GLiNER and PyTorch. GLiNER defaults to CPU for portability.
Set `GLINER_DEVICE=cuda` for a compatible CUDA environment or `GLINER_DEVICE=auto` for automatic
selection.

### Reuse a workstation CUDA build of PyTorch

This project can inherit an already installed global PyTorch build, which is useful for RTX
50-series systems that require a specific CUDA build:

```powershell
uv venv .venv --system-site-packages --prompt FinBrain
& .\.venv\Scripts\Activate.ps1
Set-Location backend
uv sync --active --extra dev --no-install-package torch
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

Use `uv run --active --no-sync ...` afterward so uv does not replace the inherited Torch build.
The demo scripts detect this root `.venv` automatically and invoke its Python executable directly,
without running dependency synchronization. After pulling dependency changes, install the new
packages explicitly while preserving Torch:

```powershell
Set-Location backend
uv sync --active --extra dev --no-install-package torch
```

To select a different compatible Python executable for the scripts, set a process-scoped override
before launching the demo:

```powershell
$env:FINBRAIN_PYTHON = "C:\path\to\python.exe"
```

## 2. Configure `backend/.env`

`backend/.env` is ignored by Git. Never commit API keys, Telegram tokens, email credentials,
database passwords, or `TOKEN_ROOT_SECRET`.

Generate a stable 32-byte root secret in PowerShell:

```powershell
[Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLower()
```

Generate three independent values. `TOKEN_ROOT_SECRET` protects application fingerprints and actor
references. `TOKEN_HASH_SECRET` fixes token identity so rotation does not change tokens.
`VAULT_MASTER_KEY` wraps random database-resident vault generations. Do not rotate the master key
by editing the environment; use the documented vault-generation rotation command.

Minimum local AI configuration:

```dotenv
TOKEN_ROOT_SECRET=your-generated-secret
TOKEN_HASH_SECRET=your-independent-stable-token-secret
VAULT_MASTER_KEY=your-independent-vault-wrapping-secret
VAULT_AUTO_ROTATION_ENABLED=true
VAULT_ROTATION_INTERVAL_DAYS=30
MORPHEUS_API_KEY=your-morpheus-key
MORPHEUS_BASE_URL=https://api.mor.org/api/v1
MORPHEUS_MODEL=deepseek-v4-flash
GEMINI_API_KEY=your-gemini-key
GEMINI_REASONING_MODEL=gemini-3.6-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
ALLOW_OFFLINE_DEMO=true
LOG_LEVEL=INFO
SENTRY_DSN=
SENTRY_ENVIRONMENT=development
SENTRY_TRACES_SAMPLE_RATE=0.0
```

`LOG_LEVEL` controls the backend's structured JSON logging (stdout, one JSON object per line —
no config needed for a log aggregator to ingest it). `SENTRY_DSN` is optional and off by default;
set it to enable backend error tracking (`send_default_pii` stays `False` regardless, since
FinBrain's whole design is keeping PII behind tokens — review Sentry's own scrubbing rules before
relying on it in production). The frontend has an equivalent, independent gate:
`VITE_SENTRY_DSN`/`VITE_SENTRY_ENVIRONMENT`/`VITE_SENTRY_TRACES_SAMPLE_RATE` in
`frontend/.env`.

Morpheus is preferred for protected summaries, cited answers, and recommendations. Gemini is the
preferred reasoning and embedding provider. With no API keys, SQLite (and Postgres, in offline
demo mode) fall back to deterministic offline summaries and 768-dimensional offline embeddings,
matching Supabase's `vector(768)` column width so semantic retrieval stays testable without a
Gemini key.

Verify Gemini from `backend`:

```powershell
uv run --active --no-sync python -m scripts.check_gemini
```

## 3. Choose the database

### Local SQLite

The default environment value is:

```dotenv
DATABASE_URL=sqlite:///./finbrain.db
```

SQLite tables are initialized by application startup. Seed the demonstration records from
`backend`:

```powershell
uv run --active --no-sync python -m seed.seed_data
```

### Supabase Postgres

1. Create a Supabase project near the intended users.
2. Keep **Enable Data API** enabled if desired, disable automatic table exposure, and enable
   automatic RLS. FinBrain's migrations also force RLS and revoke Data API grants.
3. From the repository root, authenticate and link the CLI:

```powershell
npx.cmd supabase login
npx.cmd supabase link --project-ref YOUR_PROJECT_REF
npx.cmd supabase db push
```

Alternatively, apply every file in `supabase/migrations` through the SQL editor in timestamp order.

4. Copy the exact URI from **Supabase Dashboard > Connect** into `backend/.env`. Use SQLAlchemy's
   psycopg scheme and TLS:

```dotenv
DATABASE_URL=postgresql+psycopg://postgres.PROJECT_REF:URL_ENCODED_PASSWORD@POOLER_HOST:5432/postgres?sslmode=require
```

Use the direct connection when IPv6 is available or Supavisor session mode on port 5432 for a
persistent IPv4 backend. The frontend uses only the project URL and publishable key for Supabase
Auth; never expose the database URI, secret key, or service-role key.

Configure Supabase Auth, provision users, enable the access-token hook, and add the backend and
frontend environment values described in [AUTH_SETUP.md](./AUTH_SETUP.md).

5. Verify the schema and seed from `backend`:

```powershell
uv run --active --no-sync python -m scripts.check_supabase
uv run --active --no-sync python -m seed.seed_data
```

The migration set creates protected content, a safe token registry, versioned token vault, wrapped
key generations, rotation jobs, audit, connector, structured-batch, conversation,
recommendation, evidence, decision, and workflow-audit tables. It also installs pgvector, the
`vector(768)` column, the HNSW index, JSONB role lists, forced RLS, non-bypass database roles,
append-only audit triggers, and the `started_at` heartbeat column used by the `/status` service
page.

See [infra/supabase/README.md](./infra/supabase/README.md) for connection and security details.

### Staging environment

Local development and production currently run against different databases (local SQLite by
default, or your own Postgres instance), but there is no dedicated staging project yet — anyone
testing against a real Supabase/Postgres instance today is testing against the same project the
deployed app uses. To set up a proper staging tier:

1. Create a second Supabase project (same steps as above), named e.g. `finbrain-staging`.
2. Push the same migrations to it (`npx.cmd supabase link --project-ref STAGING_PROJECT_REF && npx.cmd supabase db push`).
3. Point a separate `backend/.env.staging` (or CI secrets) at its connection string — never reuse
   the production `DATABASE_URL` for anything other than the deployed Railway service.
4. Seed it independently (`python -m seed.seed_data`) — staging data should never be copied from
   production.

This staging project is what CI, pre-release manual testing, and any invasive schema work (like a
multi-tenancy retrofit) should run against first, before touching the production database.

## CI

`.github/workflows/ci.yml` runs on every push and pull request: backend lint (`ruff check`) and the
full test suite (`pytest`, against SQLite — no secrets required), plus frontend typecheck
(`tsc -b`), lint (`eslint`), and a production build. It gates merges only — Railway's own git
integration still handles deployment on push to `main`.

`.github/workflows/anchor-audit-chain.yml` is a separate, scheduled workflow (daily, plus manual
`workflow_dispatch`) that writes each tenant's current audit/workflow hash-chain tail to
`audit-anchors/<date>.json` and commits it back to this repository. The point is tamper evidence:
the credential that pushes that commit (the GitHub Actions token) is entirely separate from the
app's own `DATABASE_URL`, so a fully compromised running app cannot silently rewrite an anchor the
way it could rewrite a Postgres row — doing so would need a force-push, an unmistakably visible act
in this repository's history. `backend/scripts/verify_audit_anchors.py` checks every committed
anchor file against the live chain and reports any that no longer match.

**Not wired up automatically** — this workflow needs a repository secret
`PRODUCTION_DATABASE_URL` (read access to the live Supabase project is enough; the workflow never
writes to the database) added under Settings → Secrets and variables → Actions before its schedule
will do anything useful.

## 4. Run FinBrain

### One-command demonstration

From the repository root:

```powershell
& .\scripts\prepare_demo.ps1
& .\scripts\run_demo.ps1
```

`prepare_demo.ps1` validates local dependencies and non-empty configuration without displaying
secrets, prewarms GLiNER, checks configured services, runs tests, and builds the frontend. It never
resets or seeds the database. For a local syntax/dependency rehearsal without network calls, use
`-SkipNetworkChecks`; the normal judging preparation should run without that switch.

This starts:

- Frontend: <http://127.0.0.1:5173>
- API and Swagger documentation: <http://127.0.0.1:8000/docs>
- Service status page: <http://127.0.0.1:8000/status>
- Telegram long-polling worker
- Email polling worker when `EMAIL_CONNECTOR_ENABLED=true`

Check and stop the tracked processes:

```powershell
& .\scripts\check_demo.ps1
& .\scripts\stop_demo.ps1
```

The launcher requires `backend/.env`, installed frontend dependencies, free ports 8000 and 5173,
and one usable Python strategy: `FINBRAIN_PYTHON`, the root `.venv`, or `uv` on PATH. Direct Python
strategies never synchronize dependencies; the uv fallback creates and synchronizes the backend
environment automatically on first run. The selected strategy is printed during startup. The
launcher records validated process ownership and writes privacy-safe diagnostics to
`.runtime/logs`. The stop script validates PID start time, executable, and descendant ancestry
before stopping anything, then verifies both ports are free.

The local launcher and checker validate connector workers through their tracked process identity.
Detailed Gmail and Telegram status remains behind Supabase JWT authentication in the application;
the PowerShell lifecycle scripts do not bypass those protected API routes.

Worker heartbeat rows are scoped to the current runtime instance. Local runs use `local`; Railway
automatically uses its injected `RAILWAY_SERVICE_ID`. Set `SERVICE_INSTANCE_ID` only when an
explicit stable name is preferred. This prevents local and deployed workers connected to the same
Supabase project from overwriting each other's `/status` state, and each worker restart replaces
its own `started_at` value.

The complete setup, connector, query, conversation, authorization, recommendation, audit, and
lifecycle test procedure is in [`TESTING_GUIDE.md`](./TESTING_GUIDE.md).

Synthetic judging inputs and expected outcomes are in [`demo/`](./demo). Upload
`demo/chat_upload_invoice_register.csv` through the paperclip or Protected Ingestion page, confirm the
protected preview, and use `demo/judging_questions.md` for the end-to-end conversation.

### Suggested demonstration flow

1. Sign in as finance/operations and synchronize the configured unread Gmail messages.
2. Upload `demo/chat_upload_invoice_register.csv`, inspect the protected preview, and confirm it.
3. Ask an exact question such as `Show all email sources` to demonstrate SQL-first citation cards.
4. Open a cited source to compare protected evidence with the role-authorized view.
5. Ask a cross-source analytical question from `demo/judging_questions.md` to demonstrate protected
   Morpheus reasoning and validated citations.
6. Create a recommendation from the cited result, then sign in as owner/director to approve it.
7. Open the Audit workspace to verify disclosure and workflow history.

### Run backend and frontend separately

Backend, from the repository root:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
Set-Location backend
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend, in a second terminal:

```powershell
Set-Location frontend
npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

### Deploy the backend with Docker (Railway)

The backend can run in a single Docker container that hosts the FastAPI API plus the optional
Telegram, email, and vault-rotation workers. This is the deployment path for Railway (the frontend
is hosted separately, e.g. on Vercel). The local `run_demo.ps1` remains the Windows-only launcher
and is not used inside the container.

Build the image from the repository root:

```powershell
docker build -t finbrain-backend -f Dockerfile .
```

Run it locally:

```powershell
docker run --rm -p 8000:8000 --env-file backend\.env finbrain-backend
```

The entrypoint (`docker/entrypoint.sh`) runs the same backend services as the local `run_demo.ps1`
launcher, minus the frontend (which Vercel hosts). It starts the API on `0.0.0.0:$PORT` (default
8000) as the main process, plus the Telegram long-polling worker when `TELEGRAM_BOT_TOKEN` is set,
the email worker when `EMAIL_CONNECTOR_ENABLED=true`, the resumable vault worker when
`VAULT_AUTO_ROTATION_ENABLED=true`, and the recommendations scheduler when
`RECOMMENDATIONS_AUTO_ANALYSIS_ENABLED=true` (re-runs process-recommendation analysis for every
tenant on an interval — `RECOMMENDATIONS_ANALYSIS_INTERVAL_SECONDS`, default 3600 — instead of only
on a manual "Analyze Processes" click; covers whatever source systems each tenant actually has ready
content in). Each worker runs in an auto-restart loop, so a transient worker crash is logged and
retried without taking the API down. `/health` is the container healthcheck, and `/status` renders a
service status page that reports each service's status, uptime, started-at, and last-heartbeat times
for that Railway service only.

On Railway, create a service from this repository. `railway.json` selects the Dockerfile builder and
configures the `/health` healthcheck (300s timeout so the first boot can download the GLiNER model).
Provide the same `backend/.env` values as Railway environment variables, including `DATABASE_URL`,
the distinct `TOKEN_ROOT_SECRET`, `TOKEN_HASH_SECRET`, and `VAULT_MASTER_KEY` values,
`SUPABASE_URL`/`SUPABASE_JWT_*`, `GEMINI_API_KEY`, and `MORPHEUS_API_KEY`. Optional worker settings
include `TELEGRAM_BOT_TOKEN`, `EMAIL_*`, `VAULT_AUTO_ROTATION_ENABLED` with its interval,
check-frequency, and batch-size values, and `RECOMMENDATIONS_AUTO_ANALYSIS_ENABLED` with its
interval.

Run only one long-polling worker for a given Telegram bot token. When testing Telegram locally,
disable the Railway Telegram worker or remove its `TELEGRAM_BOT_TOKEN`; when demonstrating the
deployed service, stop the local worker. Instance-scoped status prevents misleading heartbeat
overwrites, but Telegram itself still permits only one active `getUpdates` poller per bot.

The image installs a CPU-only PyTorch build (GLiNER and OCR run on CPU), so it does not ship CUDA
libraries.

### Deploy the frontend with Vercel

The frontend is a static Vite SPA deployed separately on Vercel. In the Vercel project, set the
**Root Directory** to `frontend` (the repo also contains `backend/`). `frontend/vercel.json`
selects the Vite framework and the `dist` output with an SPA fallback rewrite.

Set these build-time environment variables in Vercel:

```dotenv
VITE_API_URL=https://<your-service>.up.railway.app
VITE_SUPABASE_URL=https://<PROJECT_REF>.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=<publishable-key>
```

`VITE_API_URL` must point at the Railway backend; without it the frontend falls back to
`http://localhost:8000`. In Supabase Auth, set the **Site URL** and add the Vercel URL to
**Redirect URLs** so confirmation and OAuth links return to the app.

On the backend, set `CORS_ORIGINS` and `CORS_ORIGIN_REGEX` to include the Vercel domain, or the
browser will reject cross-origin API calls.

## Unified protected ingestion

Every adapter produces the same canonical fields:

```text
source_record_id + source_system + record_type + text + occurred_at + metadata
```

The manual proof-of-concept endpoint also accepts `role` and `refresh`:

```json
{
  "source_record_id": "crm:record-123",
  "source_system": "crm",
  "record_type": "customer_note",
  "text": "Customer Ahmad called about invoice INV-1024 for RM 4,500.",
  "occurred_at": "2026-08-14T10:30:00+08:00",
  "metadata": {
    "channel": "support"
  },
  "role": "finance_ops",
  "refresh": false
}
```

`source_record_id` must be an opaque connector identifier, never a customer name, phone number, or
email address. Adapter-defined metadata values pass through the same protection boundary as source
text. Connectors must not tokenize in the browser or duplicate backend privacy logic.

The ingestion service performs:

```text
validate and fingerprint
  -> detect and tokenize text and metadata
  -> encrypt sensitive values in the vault
  -> persist protected source
  -> summarize protected content
  -> validate summary tokens and residual PII
  -> embed protected content
  -> mark ready
```

Raw inbound content exists only in process memory during extraction and protection. It is not
written to the database, retry state, logs, or temporary files. A keyed HMAC fingerprint provides
idempotency without storing a reversible raw-content hash.

Processing states are:

- `protected`: safe persistence succeeded and enrichment is pending.
- `ready`: protected summary and embedding are available.
- `failed_enrichment`: the protected source remains available for safe retry.

## Telegram connector

Create a bot with BotFather and configure:

```dotenv
TELEGRAM_BOT_TOKEN=your-botfather-token
TELEGRAM_OPERATOR_ROLES=123456789:owner_director
```

Run the worker and send `/whoami` before adding an operator ID. Telegram access is restricted to
private chats and explicitly allowlisted numeric user IDs. Drafts remain in memory for ten minutes
by default and show a protected preview before confirmation.

```powershell
Set-Location backend
uv run python -m app.integrations.telegram.runner
```

Supported inputs include text, forwarded text, TXT, Markdown, CSV, EML, PDF, DOCX, and image files
(PNG, JPG, JPEG, WebP, BMP, TIFF). Scanned PDFs and images are processed with a local RapidOCR
fallback when the built-in text layer yields little or no text. OCR runs entirely on the machine —
no document image ever leaves the deployment.

## Gmail and IMAP connector

The connector opens the configured folder read-only and imports only unread messages newer than
its saved UID cursor. Importing does not mark a message as read. Durable HMAC receipts and the UID
cursor prevent duplicate ingestion across repeated synchronization.

For Gmail, enable two-step verification and create an app password, then configure:

```dotenv
EMAIL_CONNECTOR_ENABLED=true
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_IMAP_PORT=993
EMAIL_IMAP_USERNAME=your-account@gmail.com
EMAIL_IMAP_PASSWORD=your-16-character-app-password
EMAIL_IMAP_FOLDER=INBOX
EMAIL_IMAP_USE_SSL=true
EMAIL_SYNC_INTERVAL_SECONDS=60
EMAIL_MAX_MESSAGES_PER_SYNC=25
EMAIL_INCLUDE_ATTACHMENTS=true
```

Start the worker from `backend`:

```powershell
& uv run python -m app.integrations.email_connector.runner
```

The frontend also provides a local **Sync now** action. Marking an older message unread after the
saved UID cursor has passed it does not trigger a historical rescan. For production, replace app
password authentication with provider OAuth.

Every new single-sender Gmail address is protected before persistence and becomes the stable
endpoint of a provisional customer profile. The first message is linked immediately; later
messages from the same address reuse that profile without requiring an invoice. A protected
display-name or explicit first-person introduction may become an identity claim. Morpheus can
return that already-tokenized claim during summarization, but only validated protected tokens are
accepted and the model cannot mutate a customer row. A different later name creates an owner
review task and never silently renames the customer. Shared mailboxes and Telegram-created
profiles are intentionally outside this email-first scope.

## Tokenization and role views

Names, identifiers, contact details, accounts, addresses, organizations, and monetary values use
deterministic tenant-scoped tokens. Equivalent amounts such as `RM4,500` and `RM 4500.00` produce
the same reversible token:

```text
AMOUNT_BAND_3_b6d35bfc3e
```

The external model sees the approximate band and opaque reference, not the exact value. A general
employee sees a safe label such as `RM2.5K-5K`; finance/operations, owner/director, and compliance
roles can recover the normalized exact value through the encrypted vault. Authorized and denied
disclosures are both audited.

The database exposes safe token metadata to authenticated requests but applies `allowed_roles`
inside the token-vault RLS policy before ciphertext can be selected. An authorized value is
unwrapped only inside a short-lived disclosure session bound to the query hash, actor, role, and
stored turn. Its per-token grant is consumed once and then the session key is discarded. The AI
Exposure Receipt displays the vault generation, single-use grant count, and opaque session
reference.

Vault rows use random generation keys wrapped by `VAULT_MASTER_KEY`; each row then derives a
separate key from its token and generation. To rotate immediately from `backend`:

```powershell
uv run --active --no-sync python -m scripts.rotate_vault_key
```

Rotation activates a fresh random generation first, then re-encrypts old rows in bounded,
restart-safe batches without changing their tokens. With `VAULT_AUTO_ROTATION_ENABLED=true`,
`run_demo.ps1` starts the tracked rotation worker and `stop_demo.ps1` stops it with the other demo
processes.

The frontend's model-view toggle compares:

- **User view:** original question and role-authorized answer.
- **Model view:** tokenized question, protected answer, and protected citations exactly as the
  external model received them.

## SQL-first questions and cited analysis

The backend classifies each question into a trusted query intent and applies deterministic filters
before question tokenization changes the text. It never asks Morpheus to generate or execute SQL.
The selected intent is returned with the query response so the frontend can render the correct
result experience.

Examples:

| Question | Execution |
| --- | --- |
| `How many email records are there?` | SQL count; no model call |
| `Show all email sources` | SQL listing rendered as citation cards; no model call |
| `Summarize email sources` | SQL selects every ready email record, then Morpheus |
| `What issues need attention?` | SQL selects every ready record across all sources, then Morpheus |

Exact record listings return a concise result summary plus one compact card per matching record.
The chat does not duplicate full protected source text. Selecting a card or **Inspect cited
sources** loads that turn's evidence through the shared authorization endpoint and opens the same
drawer used by semantic intelligence answers. The drawer exposes:

- source system, record type, date, freshness, and age;
- the protected text supplied to the reasoning boundary;
- the current user's permitted, detokenized view;
- restored and withheld token counts with an access explanation.

Closing the drawer restores keyboard focus to the exact button that opened it without moving the
chat scroll position. Switching between cited records inside the drawer keeps the original opener
as the final focus target.

Morpheus may cite only supplied `SOURCE-n` identifiers. The backend rejects unknown citations,
invented protected tokens, and recognizable PII before detokenization. The response exposes the
number of records used, protected excerpts, source systems, record types, and timestamps.

## Process recommendations

An owner/director can use the Approvals workspace to analyze protected, action-required records and
persist a recommendation with its evidence, expected benefit, suggested owner, success metric,
priority, and confidence. Finance/operations, owner/director, and compliance roles can view the
result. Only an authenticated owner/director can make recommendation decisions. Supported
state changes are:

```text
proposed -> approved -> implemented
         -> rejected
```

Decision events are appended to a separate hash-chained workflow audit log.

## Unified customer intelligence and governed outreach

When `CUSTOMER_INTELLIGENCE_ENABLED=true`, FinBrain exposes a tenant-scoped customer workspace
that joins exact protected identity links across sources. Gmail can create a provisional customer
from a first-time sender; e-invoice and reviewed identities remain confirmed customer records.
Optional deterministic attention scoring is enabled with `CUSTOMER_ATTENTION_ENABLED=true`.
Selecting **Ask about this customer** binds the protected conversation to that customer instead of
relying on a name-only follow-up.

Finance or an owner can register a customer email endpoint, but its plaintext value is immediately
tokenized and stored only in the encrypted vault. An owner must verify the endpoint before a draft
can move to `pending_approval`. The customer must also be confirmed with no unresolved identity
claim. Only an owner can approve delivery:

```text
draft -> pending_approval -> approved -> sending -> sent -> replied
                         \-> rejected          \-> failed / delivery_unknown
```

Set `OUTBOUND_EMAIL_ENABLED=true` and configure the `EMAIL_SMTP_*` variables to let the existing
email worker deliver approved messages. Automated tests use a fake SMTP transport and never send
real mail. A network failure before delivery begins is recorded as `failed`; an interruption during
SMTP delivery is `delivery_unknown` and is never retried automatically. With
`EMAIL_REPLY_CORRELATION_ENABLED=true`, incoming `In-Reply-To` and `References` identifiers are
HMAC-hashed in memory and matched exactly to the outbound hash. A unique reference marks the action
`replied` only when the inbound protected sender token also equals the action's protected endpoint.
A mismatched sender is ingested but recorded as `identity_conflict`, never attached to the wrong
customer, and never changes invoice or payment state.

## Reset and verify demonstration data

Refresh known seed records after changing detection or enrichment behavior:

```powershell
Set-Location backend
uv run --active --no-sync python -m seed.seed_data --refresh
```

To clear FinBrain application rows and recreate the clean twelve-record Track 2 dataset while
preserving migrations, schema, indexes, and RLS:

```powershell
uv run --active --no-sync python -m seed.seed_data --reset --yes
uv run --active --no-sync python -m scripts.check_demo_data
```

The reset removes protected content, token registry/vault entries, wrapped key generations,
rotation jobs, connector cursors and receipts, recommendations, and audit history. It then creates
a fresh active vault generation and seeds email, Telegram, CRM, bank CSV, meeting-note, and
support-ticket records through the real protected ingestion service.

## Verification

Backend:

```powershell
Set-Location backend
uv run --active --no-sync python -m pytest
uv run --active --no-sync python -m ruff check app tests seed scripts
uv run --active --no-sync python -m scripts.check_supabase
uv run --active --no-sync python -m scripts.check_demo_data
```

Frontend:

```powershell
Set-Location frontend
npm.cmd run lint
npm.cmd run build
```

Latest verified local result: **122 backend tests passed**, Ruff passed, frontend ESLint reported 0
errors and 6 existing Fast Refresh warnings, and the frontend production build passed. Exact
SQL-first listings were verified with compact citation cards, lazy authorized evidence, and stable
drawer focus/scroll behavior. Two live acceptance journeys also completed from a cited query
through recommendation approval; the final structured-brief request ran in `morpheus` mode and
returned a validated five-claim protected brief.

## What is live versus demonstrated

- Suggested questions are curated interface shortcuts, but sending one uses the same live `/query`
  route as manually typed text.
- Current records are retrieved from the configured database at request time. Citations are mapped
  to the retrieved records used by that turn; they are not prewritten answer footnotes.
- Semantic questions use Morpheus when available, then Gemini, then the explicitly reported
  `offline-demo` fallback. Exact counts and simple listings deliberately use `structured-filter`
  without an external AI call.
- The response's AI Exposure Receipt reports the executed mode, model, source count, protected
  token counts, role, and whether external AI was actually used.
- Workflow events, query references, entry hashes, and chain verification are computed and stored
  by the backend. They are not generated by the Audit page.
- Seed records and demonstration accounts are synthetic. User identity is verified by Supabase;
  roles are loaded from the backend-owned `user_roles` table.
- The audit chains are hash-linked and protected from update/delete through database triggers, but
  are not externally anchored or digitally signed. A privileged database administrator remains
  inside the trust boundary.

## Important proof-of-concept boundaries

- Supabase JWT authentication and backend role authorization are implemented. Multi-tenant
  organization isolation is still deferred.
- The FastAPI backend uses a trusted server-side database connection.
- Raw input is protected in process memory, but production threat modeling and operational controls
  remain necessary.
- Finance and e-invoice screens still contain demonstration-only data.
- Chat file selection supports protected preview and confirmed ingestion for the documented file
  types; merely selecting a file does not commit it until the user confirms.
- The web-search control is visual only.
- Live WhatsApp Business, banking APIs, and Google Drive/SharePoint connectors are deferred.
  Scanned-image OCR is implemented locally with RapidOCR; cloud OCR providers are deferred.
- Email uses IMAP app-password authentication rather than provider OAuth.
- The current complete-record analytical policy prioritizes demo correctness over production-scale
  latency and context cost.
- Automatic vault-generation rotation is implemented; production still requires a managed KMS or
  HSM for the wrapping key, backups, monitoring, rate limits,
  incident response, formal PDPA review, and adversarial privacy testing.

For implementation history and team handoff, see:

- [Customer intelligence and governed outreach guide](./CUSTOMER_OUTREACH_GUIDE.md)
- [Current project progress](./PROGRESS.md)
- [Five-feature completion report](./FIVE_FEATURE_COMPLETION_REPORT.md)
- [Five-feature implementation plan](./FIVE_FEATURE_IMPLEMENTATION_PLAN.md)
- [Original platform implementation plan](./finbrain-os-implementation-plan.md)
