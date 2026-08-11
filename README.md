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

The conventional `.venv` environment uses `FinBrain` as its displayed prompt name. In PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& .\.venv\Scripts\Activate.ps1
Copy-Item backend\.env.example backend\.env
cd backend
uv sync --active --extra dev
uv run --active python -m seed.seed_data
```

## Launch

Backend, from the repository root:

```powershell
Set-ExecutionPolicy -Scope Process RemoteSigned; & .\.venv\Scripts\Activate.ps1; Set-Location backend; uv run --active uvicorn app.main:app --reload --port 8000
```

Frontend, in another terminal from the repository root:

```powershell
Set-Location frontend; npm.cmd run dev
```

Open <http://localhost:5173>. API documentation is available at <http://localhost:8000/docs>.

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
uv run --active python -m scripts.check_gemini
```

The local database seeded in offline mode contains incompatible fallback embeddings. After the
connectivity check succeeds, recreate the sample-only database once from the `backend` directory:

```powershell
Remove-Item -LiteralPath '.\finbrain.db' -Force
uv run --active python -m seed.seed_data
```

GLiNER is an optional, comparatively large dependency:

```powershell
cd backend
uv sync --active --extra ml --extra dev
```

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
uv run --active python -m scripts.check_supabase
uv run --active python -m seed.seed_data
```

See [`infra/supabase/README.md`](./infra/supabase/README.md) for connection modes, RLS boundaries,
and deployment details.

## Verification

```powershell
cd backend
uv run --active python -m pytest
uv run --active python -m ruff check .

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
