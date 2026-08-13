# Supabase deployment

The backend now supports Supabase Postgres directly through SQLAlchemy, psycopg 3, and pgvector.
SQLite remains the zero-configuration local default.

## 1. Create and migrate a Supabase project

Create a project, then apply the migration using either method:

- Supabase CLI: from the repository root, link the project and run `npx supabase db push`.
- SQL Editor: run all files under `../../supabase/migrations/` in timestamp order as the database
  owner, including the Telegram capture and Track 2 recommendation migrations.

The migrations install pgvector, create the three FinBrain tables, add the unified-ingestion
columns and constraints, build the operational indexes, enable and force RLS, and default the Data
API to no table access. `npx supabase db push` applies every pending timestamped migration after the
project is linked.

Application startup creates tables only for SQLite. Supabase/PostgreSQL schema changes must always
be applied through timestamped migrations so the remote schema and CLI migration history cannot
drift apart.

## 2. Configure the backend connection

In the Supabase dashboard, choose **Connect** and copy the exact connection URI. For this persistent
FastAPI backend:

- Prefer the direct connection when the host supports IPv6.
- Use Supavisor **session mode** on port 5432 when the host is IPv4-only.
- Use transaction mode on port 6543 only for serverless deployments. FinBrain disables psycopg
  prepared statements automatically for a `:6543` connection.

Put the URI only in the ignored `backend/.env` file. Use the psycopg SQLAlchemy scheme and require
TLS:

```dotenv
DATABASE_URL=postgresql+psycopg://postgres.PROJECT_REF:URL_ENCODED_PASSWORD@POOLER_HOST:5432/postgres?sslmode=require
```

Copy the dashboard URI instead of guessing its host, region, or username. URL-encode special
characters in the database password.

## 3. Verify and seed

From the activated backend environment:

```powershell
uv sync --active --extra dev
uv run --active --no-sync python -m scripts.check_supabase
uv run --active --no-sync python -m seed.seed_data
```

The seed command goes through the real tokenization, encryption, Gemini embedding, and native
pgvector storage path. It is idempotent by `source_record_id` and its keyed content fingerprint.

Supabase requires 768-dimensional embeddings. The deterministic offline fallback currently emits
128 dimensions for SQLite demonstrations, so configure and verify Gemini before seeding Supabase.
If enrichment later becomes unavailable, the ingestion service retains the protected record with
`failed_enrichment` status for a safe retry.

Migration `202608110002_unified_ingestion.sql` adds the source-system provenance, safe JSON
metadata, protected structured summaries, retryable processing states, enrichment mode, and update
timestamps. The embedding column is nullable so a protected record can be retained safely while an
external enrichment is retried.

## Security boundary

- Never expose the Postgres URI, database password, service-role key, or `TOKEN_ROOT_SECRET` to the
  frontend.
- The FastAPI backend currently uses a trusted server-side Postgres connection.
- RLS claims must be issued by a Custom Access Token Auth Hook or stored in `raw_app_meta_data`, not
  user-editable metadata.
- Data API grants remain revoked until tenant IDs and tenant-scoped policies are implemented.
- The UI role selector is still a demonstration mechanism; Supabase Auth is the next authorization
  phase.

`schema.sql` and `rls_policies.sql` remain as readable split references. The timestamped migration
is the deployment artifact.
