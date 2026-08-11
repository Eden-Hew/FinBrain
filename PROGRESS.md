# FinBrain OS — Project Progress

**Last updated:** 11 August 2026  
**Current phase:** Working end-to-end prototype

## Summary

FinBrain OS has progressed from an implementation plan to a runnable privacy-first customer
intelligence prototype. The system ingests sample business records, detects and encrypts sensitive
values, stores only tokenized content for retrieval, sends sanitized context to Gemini, restores
values according to the selected role, and records every disclosure decision in a tamper-evident
audit chain.

Both the backend and frontend are implemented and verified locally. Gemini is configurable through
the ignored `backend/.env` file, while an explicit offline demonstration mode remains available.

## Completed

### Backend

- FastAPI application with health, query, and compliance audit-log endpoints.
- SQLAlchemy data model backed by SQLite for the prototype.
- Seed ingestion pipeline that never persists raw inbound text.
- Deterministic tokenization using tenant-secret HMAC tokens.
- Regex detection for Malaysian NRICs, phone numbers, email addresses, monetary values, and bank
  account-like values.
- Optional GLiNER integration for context-dependent entities.
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

- Supabase/Postgres schema with pgvector storage.
- Row-level security policy templates for protected vault and audit access.
- Guardrails for the future detokenization Edge Function.
- Locked Python dependencies in `backend/uv.lock`.
- Locked frontend dependencies in `frontend/package-lock.json`.
- Root setup, launch, configuration, verification, and Gemini instructions in `README.md`.
- Local secrets, databases, environments, dependencies, caches, and builds excluded through
  `.gitignore`.

## Verification status

The latest local checks completed successfully:

- Backend Ruff lint: passed.
- Backend test suite: **7 tests passed**.
- Frontend ESLint: passed.
- Frontend TypeScript/Vite production build: passed.
- Seed ingestion: passed with sensitive values removed from stored content.
- Query endpoint: passed in offline demonstration mode and Gemini-capable configuration.
- Unauthorized audit access: correctly returns HTTP 403.
- Multi-token disclosure audit chain: verified as valid.
- User/Gemini comparison response contract: backend and frontend compile successfully.

## Local operation

Backend, from the repository root:

```powershell
Set-ExecutionPolicy -Scope Process RemoteSigned
& .\.venv\Scripts\Activate.ps1
cd backend
uv run --active uvicorn app.main:app --reload --port 8000
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
- Migrate SQLite and in-process retrieval to Supabase/Postgres and pgvector.
- Enforce vault access through production RLS and a server-controlled detokenization boundary.
- Implement live WhatsApp Business, email, banking, and document ingestion connectors.
- Add OCR for scanned documents.
- Complete GLiNER model installation, evaluation, and entity-detection tuning against representative
  Malaysian business records.
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
- The local SQLite database is ignored because it contains encrypted sample vault entries and is
  tied to the local root secret.
- The current role selector is a demonstration mechanism, not an authentication boundary.
