# FinBrain OS

FinBrain OS is a privacy-first customer-intelligence and process-optimization prototype for
Malaysian MSMEs. It brings protected records from email, Telegram, manual entry, CRM-style data,
bank exports, meeting notes, and support tickets into one queryable workspace.

Sensitive values are detected and tokenized inside the backend before any external AI call.
Morpheus analyzes protected content, Gemini creates protected embeddings, and exact values are
restored only when the selected demonstration role is authorized. Answers retain protected source
citations, while recurring issues can become evidence-backed recommendations with approval and
audit history.

## What is implemented

- Unified, source-neutral protected ingestion through FastAPI.
- Manual ingestion workspace in the React frontend.
- Protected file preview and confirmed upload for TXT, Markdown, invoice CSV, EML, PDF, and DOCX.
- Strict `invoice_register_v1` CSV parsing with stable row identity and one citation per invoice.
- Private Telegram capture bot using local long polling.
- Read-only IMAP ingestion of new unread email and supported attachments.
- Regex and optional GLiNER sensitive-data detection.
- Deterministic tenant-secret tokens and an AES-256-GCM encrypted token vault.
- Reversible, band-aware amount tokens with role-gated exact disclosure.
- Supabase Postgres, pgvector, HNSW indexing, forced RLS, and revoked Data API grants.
- Shared SQL-first counts, listings, date/type/category/action/metadata filters, and complete
  analytical record selection.
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
- Four explicit unauthenticated demonstration personas matching backend authorization roles.
- Twelve-record reset-safe demonstration dataset spanning six source systems.

## Current architecture

```text
Telegram / unread IMAP / manual UI / protected file upload / seed adapters
                         |
                         v
              CanonicalIngestionRecord
                         |
                         v
              FastAPI privacy boundary
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
                              audited response
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
uv venv .venv --prompt FinBrain
& .\.venv\Scripts\Activate.ps1
Copy-Item backend\.env.example backend\.env

Set-Location backend
uv sync --active --extra dev

Set-Location ..\frontend
npm.cmd ci
Set-Location ..
```

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

## 2. Configure `backend/.env`

`backend/.env` is ignored by Git. Never commit API keys, Telegram tokens, email credentials,
database passwords, or `TOKEN_ROOT_SECRET`.

Generate a stable 32-byte root secret in PowerShell:

```powershell
[Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLower()
```

Copy the output into `TOKEN_ROOT_SECRET`. Changing this secret later makes existing vault entries
undecryptable unless they are re-encrypted.

Minimum local AI configuration:

```dotenv
TOKEN_ROOT_SECRET=your-generated-secret
MORPHEUS_API_KEY=your-morpheus-key
MORPHEUS_BASE_URL=https://api.mor.org/api/v1
MORPHEUS_MODEL=deepseek-v4-flash
GEMINI_API_KEY=your-gemini-key
GEMINI_REASONING_MODEL=gemini-3.6-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
ALLOW_OFFLINE_DEMO=true
```

Morpheus is preferred for protected summaries, cited answers, and recommendations. Gemini is the
fallback reasoning provider and is currently required for 768-dimensional Supabase embeddings.
With no API keys, SQLite can use deterministic offline summaries and 128-dimensional embeddings.
Those offline embeddings are not compatible with Supabase's `vector(768)` column.

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
persistent IPv4 backend. Do not place the project URL, publishable key, or database URI in the
frontend; this backend uses the Postgres connection string.

5. Verify the schema and seed from `backend`:

```powershell
uv run --active --no-sync python -m scripts.check_supabase
uv run --active --no-sync python -m seed.seed_data
```

The migration set creates protected content, token vault, audit, connector, structured-batch,
conversation, recommendation, evidence, decision, and workflow-audit tables. It also installs
pgvector, the `vector(768)` column, the HNSW index, JSONB role lists, and forced RLS.

See [infra/supabase/README.md](./infra/supabase/README.md) for connection and security details.

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
- Telegram long-polling worker
- Email polling worker when `EMAIL_CONNECTOR_ENABLED=true`

Check and stop the tracked processes:

```powershell
& .\scripts\check_demo.ps1
& .\scripts\stop_demo.ps1
```

The launcher requires `backend/.env`, the root `.venv`, installed frontend dependencies, and free
ports 8000 and 5173. It records validated process ownership and writes privacy-safe diagnostics to
`.runtime/logs`. The stop script validates PID start time, executable, and descendant ancestry
before stopping anything, then verifies both ports are free.

The complete setup, connector, query, conversation, authorization, recommendation, audit, and
lifecycle test procedure is in [`TESTING_GUIDE.md`](./TESTING_GUIDE.md).

Synthetic judging inputs and expected outcomes are in [`demo/`](./demo). Upload
`demo/chat_upload_invoice_register.csv` through the paperclip or Protected Ingestion page, confirm the
protected preview, and use `demo/judging_questions.md` for the end-to-end conversation.

### Run backend and frontend separately

Backend, from the repository root:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& .\.venv\Scripts\Activate.ps1
Set-Location backend
uv run --active --no-sync uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend, in a second terminal:

```powershell
Set-Location frontend
npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

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
& ..\.venv\Scripts\python.exe -m app.integrations.telegram.runner
```

Supported inputs include text, forwarded text, TXT, Markdown, CSV, EML, text-based PDF, and DOCX.
OCR for scanned images and scanned PDFs is not implemented.

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
& ..\.venv\Scripts\python.exe -m app.integrations.email_connector.runner
```

The frontend also provides a local **Sync now** action. Marking an older message unread after the
saved UID cursor has passed it does not trigger a historical rescan. For production, replace app
password authentication with provider OAuth.

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

The frontend's model-view toggle compares:

- **User view:** original question and role-authorized answer.
- **Model view:** tokenized question, protected answer, and protected citations exactly as the
  external model received them.

## SQL-first questions and cited analysis

The backend interprets trusted source-system filters before question tokenization changes the text.
It does not ask Morpheus to generate or execute SQL.

Examples:

| Question | Execution |
| --- | --- |
| `How many email records are there?` | SQL count; no model call |
| `Show all email sources` | SQL listing; no model call |
| `Summarize email sources` | SQL selects every ready email record, then Morpheus |
| `What issues need attention?` | SQL selects every ready record across all sources, then Morpheus |

Morpheus may cite only supplied `SOURCE-n` identifiers. The backend rejects unknown citations,
invented protected tokens, and recognizable PII before detokenization. The response exposes the
number of records used, protected excerpts, source systems, record types, and timestamps.

## Process recommendations

An owner/director can use the Approvals workspace to analyze protected, action-required records and
persist a recommendation with its evidence, expected benefit, suggested owner, success metric,
priority, and confidence. Finance/operations, owner/director, and compliance roles can view the
result. Only the owner/director demonstration role can make recommendation decisions. Supported
state changes are:

```text
proposed -> approved -> implemented
         -> rejected
```

Decision events are appended to a separate hash-chained workflow audit log.

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

The reset removes protected content, vault entries, connector cursors and receipts,
recommendations, and audit history. It then seeds email, Telegram, CRM, bank CSV, meeting-note, and
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

Latest verified local result: **93 backend tests passed**, Ruff passed, frontend ESLint reported 0
errors and 6 existing Fast Refresh warnings, and the frontend production build passed. Two live
acceptance journeys completed from a cited query through recommendation approval. The final live
structured-brief request ran in `morpheus` mode and returned a validated five-claim protected brief.

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
- Seed records and demonstration personas are synthetic. The role selector is not a verified user
  identity, and names shown in the demo navigation are illustrative.
- The audit chains are tamper-evident application records, not externally anchored or digitally
  signed ledgers. A privileged database operator could rewrite and recompute an entire chain.

## Important proof-of-concept boundaries

- The frontend role selector and request role fields demonstrate authorization; they are not
  authentication.
- There is no tenant isolation or verified Supabase Auth/JWT role boundary yet.
- The FastAPI backend uses a trusted server-side database connection.
- Raw input is protected in process memory, but production threat modeling and operational controls
  remain necessary.
- Finance and e-invoice screens still contain demonstration-only data.
- Chat file selection supports protected preview and confirmed ingestion for the documented file
  types; merely selecting a file does not commit it until the user confirms.
- The web-search control is visual only.
- Live WhatsApp Business, banking APIs, Google Drive/SharePoint connectors, and OCR are deferred.
- Email uses IMAP app-password authentication rather than provider OAuth.
- The current complete-record analytical policy prioritizes demo correctness over production-scale
  latency and context cost.
- Production still requires managed secrets, key rotation, backups, monitoring, rate limits,
  incident response, formal PDPA review, and adversarial privacy testing.

For implementation history and team handoff, see:

- [Current project progress](./PROGRESS.md)
- [Five-feature completion report](./FIVE_FEATURE_COMPLETION_REPORT.md)
- [Five-feature implementation plan](./FIVE_FEATURE_IMPLEMENTATION_PLAN.md)
- [Original platform implementation plan](./finbrain-os-implementation-plan.md)
