# FinBrain OS — Project Progress

Last updated: 15 August 2026

## Current phase

The main hackathon implementation is complete. The project is now in final demonstration rehearsal and gap-closing mode.

FinBrain currently supports this end-to-end path:

```text
Gmail + Telegram + structured CSV + uploaded documents
    -> canonical protected ingestion
    -> sensitive-value tokenization
    -> Supabase persistence
    -> deterministic SQL filtering and counting
    -> Morpheus reasoning over protected content
    -> evidence-backed answers and recommendations
    -> role-aware disclosure, approval, and audit records
```

## Executive status

- Priority 1 — structured CSV ingestion: complete.
- Priority 2 — conversational context: complete.
- Priority 3 — protected file upload: complete.
- Priority 4 — deterministic structured queries: complete.
- Priority 5 — persona and disclosure demonstration: complete.
- Priority 6 — demo reliability: functionally complete; final full rehearsal remains.
- Five-feature governed-intelligence package: complete.
- Supabase JWT authentication and backend-owned API authorization: implemented locally; remote
  migration, signing-key selection, Auth hook enablement, and account provisioning remain.
- Backend verification: 100 tests passing.
- Backend lint: Ruff passing.
- Frontend verification: production build passing; lint has 0 errors and 6 pre-existing Fast Refresh warnings.
- Current branch: `main`.

## Priority plan comparison

| Priority | Planned outcome | Current status | Evidence |
| --- | --- | --- | --- |
| 1. Structured CSV | Convert invoice-register rows into protected, individually queryable records | Complete | Strict `invoice_register_v1` parser, row-level ingestion, batch receipts, idempotent refresh, metadata filters, and demo CSV fixtures |
| 2. Chat context | Support follow-up questions without mixing conversations or leaking protected data | Complete | Persisted conversations, six-turn context, ordinal and pronoun resolution, expiry/delete routes, and isolated citation namespaces |
| 3. File upload | Preview and commit common business files through the privacy boundary | Complete | TXT, Markdown, CSV, EML, text PDF, and DOCX preview/commit flow with bounded raw requests and preview-digest validation |
| 4. SQL-first filters | Answer counts and exact lists deterministically before LLM reasoning | Complete | Shared filter planner for source, date, record type, category, priority, action-required, status, and owner filters |
| 5. Persona demonstration | Show that the same evidence produces role-appropriate disclosure | Complete | Backend-enforced personas, disclosure policies, persona reruns, and user-facing disclaimers |
| 6. Demo reliability | Start, check, and stop the complete demo without orphaned processes | Implemented | Detached launcher wrappers, PID tracking, health checks, logs, stale-process recovery, and descendant/port cleanup |

## Work completed in the current implementation cycle

### 1. Structured spreadsheet ingestion

- Added the `invoice_register_v1` schema and strict CSV validation.
- Supports UTF-8 BOM and Windows-1252 input plus recognized column aliases.
- Enforces file, row, and field limits and returns stable invalid-row error codes.
- Produces one canonical protected record per valid invoice row.
- Stores queryable metadata including invoice status, due date, assigned owner, and protected amount band.
- Uses stable HMAC-derived batch and row identifiers for idempotent reprocessing.
- Protects every accepted row before enrichment or model processing.
- Added structured-ingestion batch persistence and receipt reporting.
- Fixed generic `CSV` queries to target spreadsheet records while preserving explicit `bank_csv` queries.
- Added a protected preview summary that clearly reports when only the first three rows are shown:

  ```text
  Showing 3 of 4 protected rows
  + 1 additional row will be ingested
  ```

### 2. Protected file upload

- Added preview and commit endpoints for TXT, Markdown, CSV, EML, text-based PDF, and DOCX files.
- Raw file content is accepted only within configured request-size limits.
- Preview responses contain protected content, not the original sensitive values.
- Commit requests are tied to the preview through a digest to prevent accidental content substitution.
- Structured CSV uploads use the authoritative row-level ingestion route.
- Document provenance includes file type and page count where available.

### 3. Conversational retrieval

- Added persisted conversation and turn tables plus create/read/delete API routes.
- Retains a bounded six-turn context window.
- Follow-up questions can resolve prior entities, previously listed source sets, and ordinal references such as “the third one.”
- Bare references such as “describe that” resolve against the immediately relevant prior result.
- Count responses preserve the eligible source set in hidden conversation state without falsely displaying citations.
- Citation numbering remains isolated to each answer.
- Expired or deleted conversations no longer contribute context.
- Model-provider failures are logged and can use the configured demo fallback without silently corrupting context.

### 4. SQL-first question handling

- Added a shared structured-filter planner used before semantic retrieval.
- Supports deterministic source-system counts and lists.
- Supports filters for dates, record types, categories, priority, action-required state, spreadsheet status, and assigned/unassigned owners.
- Exact counts are answered from the database without asking Morpheus to estimate from a limited retrieval set.
- Exact record listings render compact citation cards backed by the shared lazy authorized-evidence
  drawer instead of duplicating full source text in the chat answer.
- Eligible analytic result sets are processed in bounded batches instead of the former five-source cap.
- Natural-language summaries still go to Morpheus after the database establishes the complete eligible record set.

### 5. Role-aware answers

- Added exact backend role definitions and permissions for the demonstration personas.
- The backend, rather than the browser alone, controls disclosure of restored sensitive values.
- The frontend can rerun the same question under the selected persona.
- The interface distinguishes the authorized user view from the protected model view.
- Persona disclaimers make the proof-of-concept security boundary explicit.

### 6. Gmail and Telegram ingestion

- Gmail ingestion is read-only and limited to unread inbox messages.
- Durable Gmail receipts and UID cursors prevent already processed messages from being duplicated.
- Terminal UIDs are excluded on later polling cycles, including messages that previously failed permanently.
- The verified Gmail rehearsal processed six messages into six ready email records with six receipts and one attachment.
- A repeated synchronization examined zero already-processed messages.
- The seed workflow can preserve live email data with `--exclude-source email`.
- Telegram remains connected to the same canonical protected-ingestion path.

### 7. Demo process lifecycle

- `scripts/run_demo.ps1` launches frontend, backend, Telegram, and Gmail workers without binding their standard input to the interactive terminal.
- Generated `.runtime/*.launch.cmd` wrappers redirect input from `NUL` and capture logs.
- Startup reports component progress and detects early worker exits.
- PID tracking and stale-PID recovery were added.
- `scripts/check_demo.ps1` reports backend/frontend health and validates configured Telegram and
  Gmail workers through the local PID registry; detailed connector status remains JWT-protected.
- `scripts/stop_demo.ps1` stops tracked process trees and clears remaining demo listeners on the configured ports.
- A verified lifecycle run returned control to PowerShell in approximately 6.6 seconds, passed health checks, and stopped without leaving listeners or PID files.

### 8. Test and demonstration assets

- Added dedicated CSV fixtures for direct upload and Gmail attachment testing.
- Expanded `TESTING_GUIDE.md` with ingestion, query, persona, conversation, recommendation, audit, and lifecycle checks.
- Added regression coverage for CSV parsing, upload protection, conversation references, SQL filters, persona disclosure, Gmail idempotency, and process lifecycle behavior.
- Reduced GLiNER false positives for structural terms such as `Customer` and `Unassigned`.

### 9. Governed customer-intelligence package

- Added a persisted protected Customer Intelligence Brief with cited claims, timeline, missing
  information, status, and recommended action.
- Added a lazy Evidence Drawer with protected and role-authorized views, freshness, and disclosure
  counts.
- Added an AI Exposure Receipt that distinguishes `morpheus`, `gemini`, `offline-demo`, and
  deterministic `structured-filter` execution.
- Added compliance-only role comparison over one stored protected result without rerunning AI.
- Added query-originated recommendation creation with exact turn, query-hash, and citation lineage.
- Applied migration `202608150001_query_recommendation_lineage.sql`.
- Redesigned Audit so disclosure decisions and workflow events are separate, independently
  verified streams. Query references and real entry hashes are visible, while full previous and
  entry hashes are inspectable per event.
- Completed two live journeys from a cited query through owner approval; the final provider-backed
  brief ran in `morpheus` mode.

### 10. Supabase authentication and API authorization

- Added Supabase email/password session management to the React frontend.
- Added asymmetric Supabase JWT verification through the project JWKS endpoint.
- Added a backend-authoritative `user_roles` table and Custom Access Token Hook migration.
- Removed caller-selected roles from query, ingestion, upload, conversation, recommendation, and
  audit API contracts.
- Added route-level permission dependencies and HTTP 401/403 behavior.
- Bound conversations, citations, and query-originated recommendations to verified users.
- Added privacy-safe authenticated actor references to disclosure and workflow audit events.
- Replaced the global persona switcher with a read-only authenticated-role display; compliance
  role comparison remains an explicit policy simulation.
- Added JWT, stale-claim, provisioning, permission, and cross-user ownership tests.

## Verified demonstration state

The latest clean Gmail rehearsal produced:

- 6 Gmail messages examined.
- 6 email records protected and ready.
- 0 failed messages.
- 6 durable Gmail receipts.
- 1 processed attachment.
- 0 duplicate records on the next synchronization.

The clean seeded and Gmail-backed Supabase state contained 15 ready records at verification time:

- 9 non-email seed records.
- 6 live Gmail records.

The five-turn conversation replay verified:

1. An email-source count returned six database-verified records.
2. A follow-up referring to “them” retained the same six-source context.
3. “Describe each” summarized the complete eligible set rather than stopping at five.
4. A customer-specific question narrowed retrieval to the correct email.
5. “The third one” and then “describe that” both resolved to the intended prior record.

## Existing platform foundations

The earlier platform work remains in place:

- FastAPI backend with health, ask, ingestion, recommendation, audit, upload, conversation, and connector routes.
- Supabase/Postgres persistence with pgvector and HNSW indexing.
- Forced row-level security on protected tables.
- Encrypted token vault for reversible sensitive-value restoration.
- GLiNER-assisted PII detection with deterministic sensitive-value handling.
- Gemini-compatible protected summarization and embeddings.
- Morpheus proxy support for protected question answering.
- Evidence citations and model-view versus authorized-user-view comparison.
- Recommendation drafting, approval, implementation-state tracking, and audit chains.
- React frontend for chat, ingestion, uploads, role switching, recommendations, and evidence inspection.

## Database migrations

The active migration sequence includes:

- Core protected content, token vault, and audit tables.
- Canonical ingestion fields and durable connector receipts.
- Recommendation workflow tables.
- Structured-ingestion batch support.
- Persisted conversation and turn support.
- Protected brief persistence and recommendation-to-query lineage.

The Supabase checks verify PostgreSQL connectivity, pgvector, expected vector dimensions, indexes, JSON role lists, and forced RLS.

## Remaining before the hackathon demonstration

These are rehearsal and polish items, not missing core architecture:

1. Run one uninterrupted judging rehearsal from a clean database:
   - ingest six Gmail messages;
   - receive one live Telegram record;
   - upload and commit the chat-side CSV;
   - upload one ordinary document;
   - demonstrate exact SQL counts and cross-source summaries;
   - demonstrate conversational follow-ups;
   - switch personas and compare disclosure;
   - create, approve, and mark a recommendation implemented;
   - inspect the resulting audit trail.
2. Repeat the complete start -> check -> stop -> second start cycle once more under presentation conditions.
3. Record or prepare a deterministic fallback demonstration in case Gmail, Telegram, Supabase, or Morpheus is unavailable at judging time.
4. Optionally add `GET /structured-ingestion-batches/{batch_ref}`. Current upload responses already return synchronous batch status, so this is not required for the demo.
5. Optionally split Gmail CSV attachments into row-level spreadsheet records. Direct CSV upload is currently the authoritative structured path; Gmail attachments remain represented within the email ingestion record.
6. Optionally make individual PDF pages separately citable. PDF page count and extracted page markers are retained, but pages are not yet stored as separate source records.

## Intentionally deferred beyond the hackathon

- Multi-tenant organization membership and production account lifecycle administration.
- Multi-tenant organization isolation and production RLS policies.
- Arbitrary user-defined spreadsheet schemas.
- OCR for scanned PDFs and images.
- WhatsApp and additional enterprise connectors.
- Google Drive, OneDrive, and SharePoint OAuth ingestion.
- Banking and accounting APIs.
- Production key rotation and secret-management infrastructure.
- Large-scale vector-index tuning and background job orchestration.
- Kubernetes or other production deployment infrastructure.
- External task-management integrations.
- Full monitoring, alerting, retention, and compliance operations.

## Local verification

From the repository root with the `FinBrain` virtual environment active:

```powershell
uv run --active --project backend pytest backend/tests
uv run --active --project backend ruff check backend
Set-Location frontend
npm run lint
npm run build
Set-Location ..
```

Run the integrated demonstration:

```powershell
& .\scripts\run_demo.ps1
& .\scripts\check_demo.ps1
& .\scripts\stop_demo.ps1
```

Detailed manual scenarios and fixtures are documented in `TESTING_GUIDE.md`.

## Security boundary

- Raw sensitive content is submitted only to the trusted FastAPI backend.
- Detection and tokenization occur before Gemini or Morpheus receives content.
- External model providers receive protected text and protected metadata.
- Original values are encrypted in the token vault and restored only when the selected backend role permits disclosure.
- Supabase Auth now verifies browser identities with asymmetric JWTs, and FastAPI derives each
  request's role from the backend-controlled user-role assignment.
- Suggested prompts are static shortcuts, but submitted answers, citations, exposure receipts,
  workflow events, and audit hashes come from the live backend path.
- Hash chains are tamper-evident rather than tamper-proof: they detect an unrecomputed edit or gap,
  but are not signed or anchored outside the application database.

## 2026-08-17 — versioned vault security

- Split stable HMAC token identity from vault wrapping secrets.
- Added random wrapped vault generations and per-token HKDF-derived AES-256-GCM keys.
- Bound ciphertext authentication to token, entity type, source record, and key version.
- Added safe format-shaped token metadata separate from ciphertext-bearing vault rows.
- Added PostgreSQL non-bypass application and worker roles; vault RLS now checks `allowed_roles`
  before returning ciphertext.
- Added query/actor/role/turn-bound ephemeral disclosure sessions and replay-resistant single-use
  grants.
- Added resumable bounded vault re-encryption, manual rotation, and an optional tracked automatic
  rotation worker.
- Added append-only database triggers and serialized hash-chain appends for disclosure and workflow
  audits.
- Extended schema/demo checks and the frontend AI Exposure Receipt with vault generation and
  disclosure-session evidence.
- Local verification: 115 backend tests pass and Ruff reports no errors.
- Live Supabase verification completed on 2026-08-17: the clean 12-record seed produced 28
  protected vault rows, general-employee RLS exposed 20 ciphertext rows while compliance exposed
  all 28, and a v1 -> v2 rotation re-encrypted all 28 rows with no incomplete jobs or invalid audit
  chains.
