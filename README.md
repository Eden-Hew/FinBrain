# FinBrain OS

FinBrain OS is a privacy-first customer-intelligence prototype for Malaysian MSMEs. It ingests
business records, replaces sensitive values before AI processing, retrieves relevant protected
context, and restores values only when the requesting role is authorized. Every disclosure decision
is written to a hash-chained audit log.

## Architecture

```text
raw record (memory only)
  → regex + optional GLiNER detection
  → deterministic tokens + encrypted vault
  → sanitized embeddings and retrieval
  → Gemini reasoning over tokens
  → role-gated detokenization
  → verifiable audit trail
```

Questions pass through the same tokenization boundary as ingested records, so user-supplied PII is
not sent directly to Gemini either.

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
```

## Launch

Backend, from the repository root:

```powershell
Set-ExecutionPolicy -Scope Process RemoteSigned; & .\.venv\Scripts\Activate.ps1; Set-Location backend; uv run --active --no-sync uvicorn app.main:app --reload --port 8000
```

Frontend, in another terminal from the repository root:

```powershell
Set-Location frontend; npm.cmd run dev
```

Open <http://localhost:5173>. API documentation is available at <http://localhost:8000/docs>.

## Unified protected ingestion

Every source adapter must convert its input into the same `CanonicalIngestionRecord` contract:

```text
source_record_id + source_system + record_type + text + occurred_at + metadata
```

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

Raw source text exists only in process memory during detection. It must never be written to a
database, log, retry queue, error message, or temporary file. Only protected content may cross the
Gemini boundary or be retried. A keyed HMAC fingerprint makes repeated delivery idempotent without
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

Supabase stores the sanitized source, sanitized metadata, structured protected summary, embedding,
provenance, and processing state. Sensitive fragments are stored separately as encrypted vault
entries; the complete raw source record is never stored.

## Configuration

Set `GEMINI_API_KEY` in `backend/.env` to use Gemini. Without it, the backend runs in explicit
`offline-demo` mode using deterministic local embeddings and protected-record output, allowing the
security pipeline and role behavior to be demonstrated without external services.

Create an API key in [Google AI Studio](https://aistudio.google.com/app/apikey), then edit the
ignored `backend/.env` file locally:

```dotenv
GEMINI_API_KEY=your-key-here
GEMINI_REASONING_MODEL=gemini-3.6-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
```

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
2. Run `supabase/migrations/202608110001_finbrain_initial.sql` in the SQL editor, or push it with
   `npx supabase db push` after linking the CLI.
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
- SQLite remains available for local development; Supabase uses native pgvector retrieval.
- Live WhatsApp, banking, and OCR connectors remain deferred.
- The default secret is for local demonstrations only and is reported by `/health`.

See [the implementation plan](./finbrain-os-implementation-plan.md) for the original scope and the
Supabase migration notes in [`infra/supabase`](./infra/supabase).
