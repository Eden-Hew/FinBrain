# FinBrain OS

FinBrain OS is a privacy-first customer-intelligence prototype for Malaysian MSMEs. It ingests
business records, replaces sensitive values before AI processing, retrieves relevant protected
context, and restores values only when the requesting role is authorized. Answers retain citations
to protected source records, and recurring patterns can become evidence-backed process
recommendations with human approval. Every disclosure and recommendation decision is written to a
dedicated hash-chained audit log.

## Architecture

```text
raw record (memory only)
  → regex + optional GLiNER detection
  → deterministic tokens + encrypted vault
  → sanitized embeddings and retrieval
  → Morpheus reasoning with protected citations
  → role-gated detokenization
  → recurring-problem analysis and human approval
  → verifiable disclosure and workflow audit trails
```

Questions pass through the same tokenization boundary as ingested records, so user-supplied PII is
not sent directly to an external model either. Morpheus handles protected reasoning and summaries;
Gemini produces protected retrieval embeddings.

## Local setup with uv

The conventional `.venv` environment uses `FinBrain` as its displayed prompt name. This standard
setup installs PyTorch along with GLiNER, so it works without a pre-existing global Torch install:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
uv venv .venv --prompt FinBrain
& .\.venv\Scripts\Activate.ps1
Copy-Item backend\.env.example backend\.env
cd backend
uv sync --active --extra dev
uv run --active --no-sync python -m seed.seed_data

cd ..\frontend
npm.cmd ci
```

## Launch

Backend, from the repository root:

```powershell
Set-ExecutionPolicy -Scope Process RemoteSigned; & .\.venv\Scripts\Activate.ps1; Set-Location backend; uv run --active --no-sync uvicorn app.main:app --reload --port 8000
```

Frontend, in another terminal from the repository root:

```powershell
Set-Location frontend; npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open <http://127.0.0.1:5173>. API documentation is available at
<http://127.0.0.1:8000/docs>. `--strictPort` prevents Vite from silently starting a different
copy of the application on another port.

### Telegram capture bot

The hackathon prototype can run a private Telegram capture bot locally using long polling. No
public URL, tunnel, webhook, or hosted frontend is required. Configure the ignored `backend/.env`:

```dotenv
TELEGRAM_BOT_TOKEN=your-botfather-token
TELEGRAM_OPERATOR_ROLES=123456789:owner_director
```

Before adding an operator ID, run the bot and send `/whoami`; the bootstrap command returns only
the caller's numeric Telegram ID. Start the worker from the repository root:

```powershell
Set-Location backend
& ..\.venv\Scripts\python.exe -m app.integrations.telegram.runner
```

Or start the backend, frontend, and bot together:

```powershell
& .\scripts\run_demo.ps1
```

Stop and check the demo with `scripts/stop_demo.ps1` and `scripts/check_demo.ps1`. The bot accepts
private-chat text, forwarded text, TXT, Markdown, CSV, EML, text-based PDF, and DOCX input. It
shows a protected preview before confirmation and stores the protected record before starting
Morpheus summarization and Gemini embedding. Scanned-document OCR is not included.

### Read-only email connector

The optional IMAP connector incrementally imports unread email from `INBOX` into the same canonical
ingestion boundary. It hashes mailbox and message references, never persists raw email payloads,
and can reuse the safe attachment extractors for supported files. The mailbox is opened read-only,
so importing a message does not mark it as read; durable receipts and the UID cursor prevent repeat
ingestion. Configure only the ignored `backend/.env`:

```dotenv
EMAIL_CONNECTOR_ENABLED=true
EMAIL_IMAP_HOST=imap.example.com
EMAIL_IMAP_PORT=993
EMAIL_IMAP_USERNAME=your-mailbox@example.com
EMAIL_IMAP_PASSWORD=your-provider-app-password
EMAIL_IMAP_FOLDER=INBOX
EMAIL_IMAP_USE_SSL=true
EMAIL_SYNC_INTERVAL_SECONDS=60
EMAIL_MAX_MESSAGES_PER_SYNC=25
EMAIL_INCLUDE_ATTACHMENTS=true
```

Only unread messages newer than the connector's saved UID cursor are eligible. Marking an older
message unread after the cursor has passed it does not cause a historical rescan.

For the hackathon connector, use a dedicated read-only mailbox or provider app password. Production
deployments should replace password authentication with provider OAuth. Start the optional polling
worker from `backend`:

```powershell
& ..\.venv\Scripts\python.exe -m app.integrations.email_connector.runner
```

When `EMAIL_CONNECTOR_ENABLED=true`, `scripts/run_demo.ps1` starts this worker automatically. The
ingestion workspace also exposes a local-only **Sync now** control. No email credential or mailbox
address is returned to the frontend.

## Unified protected ingestion

Every source adapter must convert its input into the same `CanonicalIngestionRecord` contract:

```text
source_record_id + source_system + record_type + text + occurred_at + metadata
```

Connectors and the manual frontend submit that contract to the generic `POST /ingestion` boundary.
The HTTP request adds the proof-of-concept `role` and `refresh` fields:

```json
{
  "source_record_id": "crm:record-123",
  "source_system": "crm",
  "record_type": "customer_note",
  "text": "Original source text that may contain sensitive values.",
  "occurred_at": "2026-08-12T10:30:00+08:00",
  "metadata": {
    "channel": "support"
  },
  "role": "finance_ops",
  "refresh": false
}
```

Source-specific connectors are responsible only for extracting text and producing this normalized
JSON. Detection and tokenization remain inside FinBrain's backend and must not be duplicated in a
browser or connector.

`source_record_id` must be an opaque connector identifier, never a phone number, email address, or
customer name. Metadata keys must be fixed adapter-defined identifiers; metadata values pass
through the same detection and tokenization boundary as content.

The shared ingestion service then runs one ordered boundary:

```text
validate and fingerprint
  -> detect and tokenize content and metadata
  -> persist protected source
  -> summarize protected text
  -> validate summary tokens and residual PII
  -> embed protected source and summary
  -> mark ready
```

Raw source text exists only in process memory during extraction and detection. It must never be
written to a database, log, retry queue, error message, or temporary file. Only protected content
may cross the external AI boundary or be retried. A keyed HMAC fingerprint makes repeated delivery idempotent without
storing a reversible hash of the raw record.

Records use the following enrichment states:

- `protected`: tokenization is safely persisted and enrichment is pending.
- `ready`: protected summary and embedding are available.
- `failed_enrichment`: protected source is retained for a safe retry; raw input is not retained.

The seed module is the first adapter and exercises this same service. Refresh its known sample
records after a detector, summarizer, or embedding change:

```powershell
uv run --active --no-sync python -m seed.seed_data --refresh
```

To deliberately replace all FinBrain application rows with the clean twelve-record Track 2 demo
dataset while preserving the Supabase schema, migrations, pgvector indexes, and RLS configuration:

```powershell
uv run --active --no-sync python -m seed.seed_data --reset --yes
uv run --active --no-sync python -m scripts.check_demo_data
```

The reset dataset spans email, Telegram, CRM, bank CSV, meeting notes, and support tickets. The
explicit `--yes` guard is required because reset removes connector cursors, receipts,
recommendations, vault entries, and audit history together with protected content.

Supabase stores the sanitized source, sanitized metadata, structured protected summary, embedding,
provenance, and processing state. Reversible sensitive fragments are stored separately as
encrypted vault entries. Exact monetary values use reversible band-aware tokens: external models
see only the safe band and opaque reference, general employees see the band, and finance,
owner/director, or compliance roles can recover the exact normalized value through an audited
vault disclosure. The complete raw source record is never stored.

### SQL-first query retrieval

`POST /query` plans trusted source-system filters before PII tokenization. Exact requests such as
`show all email sources` or `show all content where source_system is email` use direct metadata
filtering and return matching protected records without embeddings or an LLM call. Analytical
requests such as `what payment issues came from email?` apply the same SQL source filter before
reasoning, so Morpheus receives every ready email record. Questions that do not identify a source
use every ready record across all source systems.

Count questions such as `what is the total number of email sources?` use the ready-record inventory
directly and report the complete database count. Questions such as `how many source systems are
available?` count distinct ready source systems instead of records.

Every analytical request first selects all matching ready records through SQL, then sends the
complete protected evidence set to the reasoning service. Sets of up to 20 records are analyzed
directly; larger sets are summarized in protected 20-record batches and synthesized with the
original `SOURCE-n` evidence identifiers. This proof-of-concept deliberately favors complete
answers over top-k vector truncation.

### Cited cross-source answers

`POST /query` retrieves structured evidence instead of anonymous text chunks. Each protected hit
retains its source system, record type, timestamp, and opaque record ID. Morpheus must
return only supplied `SOURCE-n` citation identifiers; unknown citations, unknown privacy tokens,
and residual recognizable PII are rejected before role-gated detokenization. The frontend can
toggle between the authorized answer and exact protected model view, then inspect every cited
protected excerpt. When no evidence is available, the response explicitly sets
`insufficient_evidence=true`.

### Process recommendations and approval

An owner/director can run bounded analysis over recent ready Telegram and email records. FinBrain
groups action-required structured summaries deterministically before asking Morpheus to formulate a
recommendation from the supplied `EVIDENCE-n` records. Each persisted recommendation includes its
protected evidence, expected benefit, suggested owner, success metric, priority, and confidence.
The live Approvals workspace supports proposed → approved/rejected and approved → implemented
transitions. Every transition is persisted and appended to a separate hash-chained workflow audit
log. Roles remain proof-of-concept request fields until verified authentication is implemented.

### Proof-of-concept ingestion UI

Open the **Ingest records** workspace in the frontend to submit manual text through the backend's
`POST /ingestion` endpoint. The form accepts source provenance, an opaque record ID, optional
metadata, occurrence time, and source text. Its result compares the user-submitted text with the
protected downstream text and shows the protected summary and processing status.

For this proof of concept, the endpoint accepts the role selected in the existing UI and returns it
as `submitted_as` together with `authorization_mode: demo-role`. The ingestion service currently
removes this field before processing, so it does not authorize ingestion or change tokenization,
storage, enrichment, or vault permissions. It is an informational demonstration field and must be
replaced by a verified server-side session and ingestion authorization before commercial or
multi-user use.

## Configuration

Set `GEMINI_API_KEY` in `backend/.env` to use Gemini. Without it, the backend runs in explicit
`offline-demo` mode using deterministic local embeddings and protected-record output. The current
offline embedding is 128-dimensional and therefore supports the complete local SQLite demo, but it
is not compatible with Supabase's `vector(768)` column. A Supabase deployment must currently use
the configured Gemini embedding model; if Gemini enrichment is unavailable, protected ingestion is
retained with `failed_enrichment` status for a later retry.

Create an API key in [Google AI Studio](https://aistudio.google.com/app/apikey), then edit the
ignored `backend/.env` file locally:

```dotenv
GEMINI_API_KEY=your-key-here
GEMINI_REASONING_MODEL=gemini-3.6-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
```

`gemini-3.6-flash` is the tracked project default. The ignored local environment may override it
with another model available to the configured API key, such as `gemini-3.1-flash-lite`. Run the
connectivity checker after changing either model instead of assuming an account or region supports
the default.

Do not paste the key into source files or commit `backend/.env`. Verify both models from the
`backend` directory:

```powershell
uv run --active --no-sync python -m scripts.check_gemini
```

The local database seeded in offline mode contains incompatible fallback embeddings. After the
connectivity check succeeds, recreate the sample-only database once from the `backend` directory:

```powershell
Remove-Item -LiteralPath '.\finbrain.db' -Force
uv run --active --no-sync python -m seed.seed_data
```

GLiNER is part of the protected ingestion boundary:

```powershell
cd backend
uv sync --active --extra dev
```

GLiNER and PyTorch are both explicit project dependencies. GLiNER defaults to CPU for wider device
compatibility; this changes inference speed rather than the intended detections. Set
`GLINER_DEVICE=cuda` on a CUDA-capable workstation to accelerate it, or `GLINER_DEVICE=auto` to
select CUDA when available.

For a workstation that already has a compatible CUDA PyTorch build, such as this RTX 50-series
machine, reuse that build without changing dependency resolution for everyone else:

```powershell
uv venv .venv --system-site-packages --prompt FinBrain
& .\.venv\Scripts\Activate.ps1
cd backend
uv sync --active --extra dev --no-install-package torch
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

Use `uv run --active --no-sync ...` after this RTX-specific sync so a later command does not install
the locked default Torch package over the inherited CUDA build.

Set `ENABLE_GLINER=false` to use only deterministic structured-data detection. Before production,
replace `TOKEN_ROOT_SECRET` with at least 32 random characters, disable offline fallback, add real
authentication, and migrate the supplied schema and RLS policies to Supabase.

## Supabase/Postgres

The backend supports both SQLite and Supabase Postgres. Supabase uses native `vector(768)` storage,
an HNSW cosine index, psycopg 3, JSON role lists, and SQL-side nearest-neighbor retrieval.

1. Create a Supabase project.
2. Apply all migrations in timestamp order in the SQL editor:
   `202608110001_finbrain_initial.sql`, `202608110002_unified_ingestion.sql`,
   `202608130001_telegram_capture.sql`, and
   `202608130002_track2_recommendations.sql`, followed by
   `202608130003_connector_rls.sql`. Alternatively, link the CLI and run
   `npx supabase db push` to apply all pending migrations. PostgreSQL tables are never created by
   application startup; only SQLite uses automatic `create_all()` initialization.
3. Copy the exact **Connect** URI into the ignored `backend/.env`, using the
   `postgresql+psycopg://` scheme and `sslmode=require`.
4. For a persistent IPv4 backend, prefer Supavisor session mode on port 5432. Direct connections
   require IPv6 unless the project has the IPv4 add-on.
5. Verify and seed from `backend`:

```powershell
uv sync --active --extra dev
uv run --active --no-sync python -m scripts.check_supabase
uv run --active --no-sync python -m seed.seed_data
```

See [`infra/supabase/README.md`](./infra/supabase/README.md) for connection modes, RLS boundaries,
and deployment details.

## Verification

```powershell
cd backend
uv run --active --no-sync python -m pytest
uv run --active --no-sync python -m ruff check .

cd ..\frontend
npm.cmd run lint
npm.cmd run build
```

## Current prototype boundaries

- The UI role selector demonstrates authorization behavior; it is not authentication.
- The ingestion role is currently informational; it is not an ingestion authorization check.
- SQLite remains available for local development; Supabase uses native pgvector retrieval.
- Offline 128-dimensional embeddings are currently SQLite-only; Supabase enrichment requires the
  configured 768-dimensional Gemini embedding model.
- Manual, Telegram, and configured email ingestion call the live backend. Finance and e-invoice
  screens remain in-memory demonstration data.
- Chat answers now call the backend first, expose protected citations, and retain scripted content
  only as a fallback when the local backend is unavailable.
- Process recommendations, evidence, approvals, and workflow audit events are persisted. Their
  request roles are still demo fields rather than verified identities.
- The Audit screen now reads live disclosure and workflow chains as compliance. It no longer claims
  sample rows are cryptographically verified.
- Chat file selection currently attaches only a filename chip, and the web-search control is a UI
  demonstration; neither performs file ingestion or web browsing yet.
- Live WhatsApp, banking, and OCR connectors remain deferred.
- The default secret is for local demonstrations only and is reported by `/health`.

See [the implementation plan](./finbrain-os-implementation-plan.md) for the original scope and the
Supabase migration notes in [`infra/supabase`](./infra/supabase).
