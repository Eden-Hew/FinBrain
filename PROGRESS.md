# FinBrain OS — Project Progress

**Last updated:** 11 August 2026  
**Current phase:** End-to-end prototype deployed to Supabase Postgres

## Summary

FinBrain OS has progressed from an implementation plan to a runnable privacy-first customer
intelligence prototype. The system ingests sample business records, detects and encrypts sensitive
values, stores only tokenized content for retrieval, sends sanitized context to Gemini, restores
values according to the selected role, and records every disclosure decision in a tamper-evident
audit chain.

Both the backend and frontend are implemented and verified locally. Gemini is configurable through
the ignored `backend/.env` file, while an explicit offline demonstration mode remains available.
The remote Supabase project is linked through the CLI, migrated, verified, and seeded.

## Completed

### Backend

- FastAPI application with health, query, and compliance audit-log endpoints.
- Portable SQLAlchemy data model supporting SQLite locally and Supabase Postgres remotely.
- Seed ingestion pipeline that never persists raw inbound text.
- Canonical source-neutral ingestion contract shared by seed data and future connectors.
- Protected metadata tokenization, keyed content fingerprints, automatic change detection, and
  idempotent delivery handling.
- Sanitized-only Gemini structured summarization with exact-token and residual-PII validation.
- Retryable `protected`, `ready`, and `failed_enrichment` states that retain no raw source payload.
- Deterministic tokenization using tenant-secret HMAC tokens.
- Regex detection for Malaysian NRICs, phone numbers, email addresses, monetary values, and bank
  account-like values.
- GLiNER integration for context-dependent entities, running on the RTX 5060 through the global
  CUDA 12.8 PyTorch build without installing a second Torch distribution.
- PyTorch is an explicit locked project dependency for standard installations; the RTX workstation
  alone skips its managed installation and inherits the verified global CUDA build.
- Portable GLiNER device configuration defaults to CPU, with explicit `cuda` and automatic
  selection available for accelerated deployments.
- AES-256-GCM token vault with HKDF-derived encryption keys.
- Amount generalization into non-reversible value bands.
- Role-based detokenization for general employee, finance/operations, owner/director, and compliance
  roles.
- Query-side tokenization so sensitive values typed by a user are also hidden before external model
  processing.
- Gemini reasoning and embedding integration through the official `google-genai` SDK.
- Configurable reasoning model, currently defaulting to `gemini-3.6-flash`.
- Text retrieval embeddings using `gemini-embedding-001` at 768 dimensions.
- Deterministic local embedding and reasoning fallback for offline demonstrations.
- Unknown model-token validation before detokenization.
- Hash-chained audit log with verification of the complete event chain.
- Gemini connectivity checker at `backend/scripts/check_gemini.py`.
- Native Postgres `vector(768)` storage and SQL cosine-distance retrieval.
- psycopg 3 support for direct, Supavisor session, and transaction-pooler connections.
- Supabase database connectivity and schema checker at `backend/scripts/check_supabase.py`.
- Live Supabase Postgres 17.6 deployment with pgvector 0.8.2.

### Frontend

- React, TypeScript, and Vite application.
- Responsive FinBrain interface with customer-intelligence positioning.
- Role selector demonstrating permission-dependent disclosure.
- Chat interface with loading, errors, prompts, and response metadata.
- User/Gemini comparison toggle:
  - **User view** shows the original question and role-authorized response.
  - **Gemini view** shows the sanitized question and exact tokenized model response.
- Compliance-only audit viewer with chain-integrity status.
- Production frontend build configuration and ESLint checks.

### Infrastructure and documentation

- Deployable timestamped Supabase migration with pgvector and HNSW cosine indexing.
- Unified-ingestion Supabase migration with provenance, JSONB metadata and summaries, processing
  status, nullable retry-safe embeddings, and operational indexes.
- Supabase CLI project configuration with synchronized local and remote migration history.
- Default-deny Data API grants with forced RLS on business, vault, and audit tables.
- Role-aware vault and compliance audit policy templates using verified `user_role` JWT claims.
- Guardrails for the future detokenization Edge Function.
- Locked Python dependencies in `backend/uv.lock`.
- Locked frontend dependencies in `frontend/package-lock.json`.
- Root setup, launch, configuration, verification, and Gemini instructions in `README.md`.
- Local secrets, databases, environments, dependencies, caches, and builds excluded through
  `.gitignore`.

## Verification status

The latest local checks completed successfully:

- Backend Ruff lint: passed.
- Backend test suite: **19 tests passed**, including protected-boundary privacy, metadata
  tokenization, idempotency, automatic refresh, failed-enrichment persistence, summary validation,
  opaque source-ID enforcement, retrieval composition, and SQLite/Postgres portability coverage.
- Global PyTorch reuse: verified with PyTorch `2.12.0.dev20260322+cu128`, CUDA 12.8, and the NVIDIA
  GeForce RTX 5060 Laptop GPU; GLiNER loaded on `cuda:0`.
- GLiNER CPU/GPU comparison: identical detections on the representative PII sample; warm inference
  measured 0.092 seconds on CPU and 0.021 seconds on GPU (approximately 4.4x GPU speedup).
- Frontend ESLint: passed.
- Frontend TypeScript/Vite production build: passed.
- Seed ingestion: passed with sensitive values removed from stored content.
- Query endpoint: passed in offline demonstration mode and Gemini-capable configuration.
- Unauthorized audit access: correctly returns HTTP 403.
- Multi-token disclosure audit chain: verified as valid.
- User/Gemini comparison response contract: backend and frontend compile successfully.
- Live Supabase schema: all three tables, `vector(768)`, JSONB roles, HNSW index, and forced RLS
  verified.
- Migrations `202608110001` and `202608110002` are synchronized in local and remote Supabase CLI
  history.
- Remote seed state after GLiNER refresh: **4 tokenized content rows**, **11 encrypted vault
  entries** (including **4 PERSON tokens**), and **0 audit events** before application queries.
- Remote sample-name verification: **0 original sample names** remain in tokenized content.
- Unified-ingestion remote verification: all **4 records ready**, all **4 structured summaries**
  generated through Gemini, all embeddings at **768 dimensions**, and keyed fingerprints and source
  provenance populated; **0 original sample names** remain across content, summaries, and metadata.
- Current remote counts: **4 protected content records**, **11 encrypted vault entries**, and **22
  existing query-disclosure audit events** with a valid hash chain; ingestion refreshes do not
  create disclosure events.

## Local operation

Backend, from the repository root:

```powershell
Set-ExecutionPolicy -Scope Process RemoteSigned
& .\.venv\Scripts\Activate.ps1
cd backend
uv run --active --no-sync uvicorn app.main:app --reload --port 8000
```

Frontend, in a second terminal from the repository root:

```powershell
cd frontend
npm.cmd run dev
```

The application is available at `http://localhost:5173`, with API documentation at
`http://localhost:8000/docs`.

## Remaining before production

- Replace the demonstration role selector with verified authentication and server-issued role
  claims.
- Add a backup and restore procedure for the Supabase database and encrypted vault.
- Enforce vault access through production RLS and a server-controlled detokenization boundary.
- Implement live WhatsApp Business, email, banking, and document ingestion connectors.
- Add OCR for scanned documents.
- Evaluate and tune GLiNER entity detection against representative Malaysian business records.
- Add detection-quality tests, prompt-injection testing, adversarial privacy tests, and broader API
  integration tests.
- Store `TOKEN_ROOT_SECRET` in a managed secret service and implement controlled key rotation and
  vault re-encryption.
- Add real tenant isolation and tenant-specific token secrets.
- Add production monitoring, rate limits, backups, incident response, and formal PDPA/DPO review.
- Evaluate token-preservation accuracy and answer quality across the intended Gemini model options
  before selecting the production model.

## Security notes

- `backend/.env` is intentionally not tracked and must never be committed.
- `TOKEN_ROOT_SECRET` must be generated once, stored securely, and kept stable; changing it makes
  existing vault values undecryptable unless they are re-encrypted.
- Any local SQLite database is ignored because it contains encrypted vault entries and is tied to
  the configured root secret.
- The current role selector is a demonstration mechanism, not an authentication boundary.
