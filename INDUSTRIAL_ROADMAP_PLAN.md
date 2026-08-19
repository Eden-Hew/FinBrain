# Industrial-standards roadmap — multi-tenancy, real retrieval, and platform hardening

## Context

After finishing the e-Invoice Readiness feature, the user asked for a senior-engineer-level assessment of what this product still lacks to be considered industrial-grade, covering both Customer Intelligence and Process Optimization. Three research passes over the live codebase confirmed the assessment with hard evidence:

- **Zero multi-tenancy**: every one of 21 RLS-protected tables is scoped only by `finbrain_role()` (business role). There is no `tenant_id`/`org_id` anywhere — not in the schema, not in JWT claims, not in Supabase Auth metadata. This is a from-scratch retrofit, not a migration.
- **"Intelligence" is filtered retrieval, not ranked retrieval**: `/query` always uses `list_eligible_hits()` (plain SQL filter, similarity hardcoded to `1.0`). A fully-built pgvector cosine-similarity function (`retrieve_hits()`, HNSW-indexed, real embedding-based ranking) exists in `app/services/retrieval.py` and is called **only by tests** — never by the live route.
- **No CI, dev and prod share one Supabase project**: confirmed by hitting the same 15-connection session pool exhaustion issue repeatedly this session, from local scripts running alongside the deployed app.
- **Recommendations are on-demand only** — no scheduled/background analysis; the only recurring-job pattern in the codebase is three sibling OS processes (`docker/entrypoint.sh` → `while True: sleep(N)` runners) for Telegram/email polling and vault rotation.
- **No observability** beyond a self-reported worker-heartbeat status page; no error tracking, no structured logging, no real dependency health checks.
- **Zero frontend test coverage** — no test runner, no config, no test files.
- **PDPA copy in the UI has no backend behind it** — no export/erasure endpoint exists.
- **The audit hash chain is self-contained** — genesis, every hash, and the verification function all live in the same Postgres database they protect; a superuser with DB access is explicitly exempted from the append-only trigger and could rewrite the whole chain undetected.

User confirmed: plan **all phases**, and treat multi-tenancy as a **full schema-wide** retrofit (not just the foundational pattern for new tables). Later phases are intentionally scoped lighter than the top three.

## Phase order and why

Environment separation + CI goes **before** multi-tenancy, even though multi-tenancy was flagged as the single biggest gap — because multi-tenancy is the highest-risk change in this plan, and right now there is no staging environment and no automated test gate to catch a bad migration before it hits the shared production database. Building the safety net first is what makes the invasive schema change survivable.

| Phase | What | Risk/effort | Depends on |
|---|---|---|---|
| 1 | CI + environment separation | Low effort, high leverage | — |
| 2 | Multi-tenancy retrofit (schema, RLS, auth, service layer) | Largest phase, multi-session | Phase 1 |
| 2b | Per-tenant integration credentials (Telegram/email) | Follow-on, flagged not built | Phase 2 |
| 3 | Real vector retrieval wired into `/query` | Medium | — (independent of tenancy) |
| 4 | Observability (logging, error tracking, real health checks) | Low-medium | — |
| 5 | Continuous process-optimization worker | Medium | Phase 2 (per-tenant scheduling) |
| 6 | Entity resolution (customer/account identity) | Medium, foundational for future CRM work | — |
| 7 | PDPA export/erasure endpoints | Low (architecture already supports crypto-erasure) | Phase 6 (for scoping "erase everything about X") |
| 8 | External audit-chain anchoring | Low effort, backlog priority | — |

---

## Phase 1 — CI + environment separation

**Environment separation**: provision a second Supabase project for staging. Local dev keeps using SQLite by default (`initialize_local_schema()` already handles this — no change needed there); a `DATABASE_URL` pointed at the staging project is what CI and pre-production manual testing use. Production Railway deployment keeps its existing project untouched. Document the three-tier setup (local SQLite → staging Supabase → production Supabase) in `backend/README.md` or `CLAUDE.md`.

**CI**: add `.github/workflows/ci.yml` — on every push/PR:
- Backend job: `uv sync --extra dev`, `ruff check .`, `pytest -q` (all against SQLite — no secrets needed, matches how the local test suite already runs).
- Frontend job: `npm ci`, `npx tsc -b`, `npm run lint`, `npm run build`.

No deploy step needed — Railway's git integration already deploys on push to `main`; CI's job is purely to gate merges, not to replace Railway's deploy trigger. This is the cheapest, lowest-risk piece of this whole plan and should land first.

## Phase 2 — Multi-tenancy retrofit

**New entity**: `tenants` table (`id uuid pk`, `name`, `slug`, `created_at`). One migration creates it and inserts a single `default` tenant row — every existing table's backfill points at this row, so existing data becomes tenant `default` with zero data loss.

**Membership becomes composite**: `user_roles` (currently `user_id` PK → single role) gets a `tenant_id` column and its primary key becomes `(user_id, tenant_id)` — this is the standard SaaS pattern (a user can belong to multiple tenants with different roles in each), not a bolt-on column on a 1:1 table. Existing rows backfill to the `default` tenant.

**JWT and auth chain** (mirrors the existing `user_role` claim exactly):
- Extend the Supabase Auth Hook `custom_access_token_hook()` (`supabase/migrations/202608150002_supabase_auth_and_user_roles.sql`) to also inject a `tenant_id` claim — for v1, a user's sole tenant from their `user_roles` membership (multi-tenant-per-user tenant *switching* UI is out of scope for this phase; the data model supports it, the UI doesn't need to yet).
- `AuthPrincipal` (`app/auth/principal.py`) gets a `tenant_id: UUID` field.
- `get_current_user()` (`app/auth/dependencies.py`) passes it through to `set_rls_context()`.

**RLS propagation** — extend `set_rls_context()`/`set_worker_context()` in `app/db.py` with a `tenant_id` param, one more `set_config('app.tenant_id', ...)` call (mirrors `app.user_id`/`app.user_role` exactly — same transaction-scoped pattern, same `after_begin` event-listener re-application). New Postgres function `finbrain_tenant_id()` in a new migration, identical shape to the existing `finbrain_user_id()`:
```sql
create or replace function public.finbrain_tenant_id()
returns uuid language sql stable set search_path = ''
as $$ select nullif(current_setting('app.tenant_id', true), '')::uuid $$;
```

**Schema-wide rollout** — every one of the 21 RLS-enabled tables (full list already enumerated during research; representative spread: `tokenized_content`, `token_vault`, `audit_log`, `conversations`, `process_recommendations`, `workflow_audit_log`, `einvoice_records`, etc.) gets, in one large migration:
1. `tenant_id uuid not null references public.tenants(id)` (denormalized onto every table, including FK-linked child tables like `recommendation_evidence`/`conversation_turns` — don't rely solely on transitive RLS through the parent; it's slower and harder to reason about).
2. Every existing `using`/`with check` clause gets `and tenant_id = public.finbrain_tenant_id()` appended.
3. An index on `tenant_id` (compound with the table's existing common filter column where one exists, e.g. `(tenant_id, status)`).

**Service layer** — this is the largest chunk of actual code-touching work, and it's necessary because of a confirmed test-harness gap: RLS never runs against SQLite (`set_rls_context()`/`set_worker_context()` both no-op on non-Postgres dialects), so the pytest suite proves isolation only through explicit Python-level filtering — exactly how `get_active_conversation()` already filters by `created_by_user_id` in the query itself, not just relying on Postgres RLS. Every service-layer query function across `app/services/` needs the same treatment: an explicit `.where(Model.tenant_id == principal.tenant_id)` clause, so tenant isolation is provably correct in tests, not just hoped-for in production.

**Test harness**: `tests/auth_support.py`'s `principal()` factory gets a `tenant_id` parameter; add a second fake tenant so cross-tenant isolation tests can assert what `test_conversation_owner_cannot_be_crossed` already proves for cross-*user* isolation, but for cross-*tenant*.

**Explicitly not built in this phase — flagged, not silently skipped**: `TELEGRAM_BOT_TOKEN`, `EMAIL_IMAP_HOST`/credentials are today global environment variables — one bot, one inbox, for the whole deployment. True multi-tenancy needs these to become per-tenant rows in a new `tenant_integration_credentials` table (encrypted via the existing vault mechanism, same pattern as `token_vault`), with each worker (`email_connector/runner.py`, `telegram/runner.py`) iterating tenants instead of reading one global env var. This is a real, separate, substantial piece of work — bundling it into Phase 2 would make the phase unbounded, so it's called out here as **Phase 2b**, to be scoped and planned on its own once Phase 2's data-isolation layer has landed and proven itself.

**Implementation status (code-level retrofit complete, not yet applied to production)** — every RLS-protected table has been resolved one of three ways:
- **Tenant-scoped** (`tenant_id` column + RLS + explicit Python-layer filtering): the `conversations`/`process_recommendations`/`einvoice_records` families (8 tables), plus `tokenized_content`, `token_vault`, `protected_token_registry`, plus `audit_log`/`workflow_audit_log` (see below) — 12 tables total, on top of the `user_roles` composite-key foundation.
- **Deliberately kept global, not tenant-scoped**: `vault_key_versions` and `vault_rotation_jobs`. These are shared vault-key-rotation infrastructure, not tenant-owned data — forcing a `tenant_id` onto them would be architecturally wrong, since a key rotation event applies to the whole vault, not to one tenant's slice of it.
- **Deferred to Phase 2b** (per-tenant integration credentials): `structured_ingestion_batches`, `integration_status`, `email_sync_state`, `email_ingestion_receipts`, `telegram_update_receipts`. There is currently only one global Telegram bot and one global email inbox to attribute rows to — tenant-scoping these tables now would not reflect reality; they become tenant-scoped naturally once Phase 2b lands per-tenant credentials.

The `audit_log`/`workflow_audit_log` hash chains needed a design change beyond a plain `tenant_id` column: `tenant_id` is **nullable** on both tables — `NULL` is reserved for genuinely system-level events (e.g. vault key rotation, which is global by the same reasoning as `vault_key_versions` above), a real tenant UUID for everything tenant-owned. The chain-tail lookup function became `finbrain_audit_tail(chain_name, tenant_id)` (2-arg, NULL-safe via `is not distinct from`), so each tenant has its own independent hash chain rather than one shared chain across all tenants — a tenant's compliance view reads both its own chain and the system chain.

A real cross-tenant token-collision security bug was also found and fixed during this work: PII token derivation (`security/tokenize.py`) previously hashed only the normalized value, so the same value (e.g. the same phone number) from two different tenants produced the identical token — meaning tenant B could theoretically hit a token minted for tenant A's data. Fixed by folding `tenant_id` into the HMAC canonical input, so tokens are unique per `(tenant_id, value)`. This required no primary-key changes downstream since the token itself now encodes tenant identity.

## Phase 3 — Real vector retrieval in `/query`

Confirmed from research: `retrieve_hits()` takes a pre-computed embedding and does real HNSW cosine-similarity search, but only supports an `source_systems` filter — it has no equivalent of `record_types`, date range, or `processing_status='ready'`. `list_eligible_hits()` has the full filter surface but zero ranking (similarity hardcoded to `1.0`).

**Bring `retrieve_hits()` to filter parity** with `QueryFilters` (record_types, occurred_from/to, metadata_equals/missing, the `processing_status='ready'` guard) so it becomes a real drop-in option, not just a narrower sibling.

**Intent-specific strategy** — this is the key design decision, informed directly by how `QueryIntent` actually behaves today:
- `SEMANTIC` (the true open-ended "ask anything" case) → switch to `retrieve_hits()`: embed the question via the existing `embed_text()` (same function ingestion already uses), fetch top-k (~8–12) by cosine similarity. This is the actual fix — right now SEMANTIC dumps every matching row to the LLM with no relevance signal at all.
- `ANALYZE_ALL` → **keep** the current unbounded `list_eligible_hits()` + 20-item batching. Its whole semantic is "every/all/entire" — truncating to top-k would silently drop data the user explicitly asked to see all of. This is not a gap to fix, it's correct as-is.
- `COUNT_RECORDS`, `LIST_RECORDS`, referential follow-ups → unchanged. These need exact/exhaustive counts and IDs, not similarity ranking; `list_eligible_hits()` is already the right tool for them.

**Embedding cost/caching**: no caching exists anywhere today (`embed_text()` hits Gemini fresh every call). Wiring it into every SEMANTIC query needs a simple cache — a small `query_embedding_cache` table (or in-memory LRU, cheaper first cut) keyed by a normalized-question hash, since repeated/similar questions are common in a chat interface.

**Fix the offline-fallback dimension mismatch**: `_offline_embedding()` produces 128-dim vectors against a `vector(768)` column — this would break outright if `retrieve_hits()` runs in offline-demo mode against real Postgres. Pad/resize the offline fallback to 768 dims so local dev without a Gemini key stays fully testable against a real pgvector column.

**Implementation status (code-level, verified locally)**: all four items above are done.
- `_offline_embedding()` now defaults to 768 dims (`EMBEDDING_DIMENSIONS` in `embeddings.py`), matching the real pgvector column width.
- Filter parity was achieved by extracting the predicate logic shared between the plain-listing and similarity-ranked paths into one function, `apply_content_filters(statement, filters)` in `query_filters.py` — `eligible_statement()` and `retrieve_hits()` both build on it now, so the two paths stay in parity by construction rather than by convention. `retrieve_hits()` takes a `filters: QueryFilters` param (default `QueryFilters()`, i.e. the old tenant-only behavior) instead of separate `tenant_id`/`source_systems` kwargs.
- `/query`'s intent dispatch in `routes/query.py` now branches SEMANTIC into its own case: it embeds the sanitized question (`embed_query_cached()`) and calls `retrieve_hits(db, embedding, k=SEMANTIC_TOP_K, filters=plan.filters)` with `SEMANTIC_TOP_K = 10`. ANALYZE_ALL is untouched, still calling `list_eligible_hits()` unbounded.
- `embed_query_cached()` (`embeddings.py`) is the "cheaper first cut" in-memory LRU (256 entries, per-process, keyed by exact sanitized-question text) rather than a `query_embedding_cache` table — sufficient for the common case of exact-repeat questions in one chat session; not durable or shared across Railway instances, which is an accepted tradeoff at this stage.
- One subtlety worth recording: `retrieve_hits()`'s Postgres branch still uses a raw `text()` fragment for the `<=>` cosine-distance operator (not the SQLAlchemy ORM column, since `TokenizedContent.embedding`'s `EmbeddingType` is a `TypeDecorator` over `Text` and doesn't expose pgvector's `.cosine_distance()` comparator) — this mirrors the pre-existing working pattern rather than introducing a new one, just extended to compose with `apply_content_filters()`'s ORM-built WHERE clause in the same statement.

124/124 backend tests passing, ruff clean. Committed (`bb0c3ee`).

## Phase 4 — Observability (lighter touch)

- Structured logging in `app/main.py` (currently unconfigured — falls through to uvicorn defaults). Standard library `logging` with a JSON formatter is enough; no need for a new dependency.
- Error tracking (Sentry's free tier is the standard choice) wired into both FastAPI (via its ASGI middleware) and the frontend.
- Deepen `/health` beyond its current hardcoded `{"status": "ok"}` — add a real DB round-trip check (`select 1`), since Railway's healthcheck currently can't detect a dead database connection at all.
- `/status` already does real heartbeat-freshness checks for workers — leave as-is; not worth adding external API pings (Telegram/Gemini/Morpheus reachability) at this stage, the cost/value isn't there yet.

**Implementation status (code-level, verified locally)**:
- `app/observability.py` (new) has `configure_logging()` (single-line JSON records to stdout via a custom `logging.Formatter`, uvicorn's own loggers rerouted through the same handler) and `init_sentry()` (no-op unless `SENTRY_DSN` is set; lazy-imports `sentry_sdk` so the no-op path never touches the package). Both are called from `main.py` at module load, before the `FastAPI(...)` app is constructed. New settings: `log_level`, `sentry_dsn`, `sentry_environment`, `sentry_traces_sample_rate`.
- `send_default_pii=False` is hardcoded, not settings-driven — this app's core design is keeping PII behind tokens, and Sentry's default capture (request bodies, stack-frame locals) works directly against that. Turning on richer capture needs to be a deliberate choice made later, not a default.
- `/health` (`main.py`) now takes a `db: Session = Depends(get_db)` and runs `select 1`; on failure it logs the exception, returns HTTP 503, and reports `{"status": "degraded", "database_reachable": false}` instead of a static `ok`. Covered by two new tests in `tests/test_health_endpoint.py` (reachable and unreachable paths, the latter via a fake session whose `.execute()` raises).
- Added `sentry-sdk[fastapi]` to `backend/pyproject.toml` and `@sentry/react` to `frontend/package.json`. Frontend gets the equivalent gate: `frontend/src/lib/observability.ts`'s `initObservability()`, called once from `main.tsx` before the render, no-ops unless `VITE_SENTRY_DSN` is set.
- Along the way, fixed a stale README claim that offline embeddings were 128-dim and incompatible with Supabase's `vector(768)` column — that was the real bug fixed in Phase 3's dimension-mismatch item; the README now reflects the actual (fixed) 768-dim behavior.
- Also fixed, since checking frontend lint as part of this phase surfaced two categories of pre-existing debt that would have failed the new Phase 1 CI frontend job on the very first run: 11 `react-hooks/refs` errors in `Landing.tsx` (fixed by destructuring `useParallax()`/`useTilt()`'s return values into individual local bindings instead of passing `heroParallax.ref` etc. directly — the compiler's ref-safety check treats any member access on an object holding a ref as a ref read, even for unrelated sibling fields) and 6 `react-hooks/set-state-in-effect` errors across `QuickActionsPalette.tsx`, `interactivity.ts`, and `Audit.tsx`. Of the six: three were genuine "derived state" patterns fixed properly (a lazy `useState` initializer for `useInView`'s reduced-motion case; splitting `QuickActionsPalette` into an always-mounted shell and an inner body that mounts fresh on each open, removing the need to reset its own state; the render-time "adjust state when a value changes" pattern for pagination reset in `Audit.tsx` and highlight reset in the palette). The remaining two (`useTypewriterDemo`, `useCountUp`) are genuinely state that must react to a changing dependency over time via a timer/animation-frame subscription, not derivable at mount — left as targeted, commented `eslint-disable-next-line` suppressions, matching the existing precedent already in that file.

126/126 backend tests passing, ruff clean. Frontend `tsc -b`, `npm run build`, and `npm run lint` all pass clean (0 errors; only pre-existing, unrelated `react-refresh/only-export-components` warnings remain). Landing page re-verified visually in a browser after the refactor — parallax, tilt, and the typewriter demo all still animate correctly.

## Phase 5 — Continuous process-optimization worker

Reuse the exact existing runner pattern (`docker/entrypoint.sh` conditional `while True: sleep(N)` worker, same shape as `rotation_runner.py`) — a new `app/services/recommendations_scheduler.py` that periodically re-runs the existing analysis logic instead of only firing from the "Analyze Processes" button. New config: `RECOMMENDATIONS_AUTO_ANALYSIS_ENABLED`, `RECOMMENDATIONS_ANALYSIS_INTERVAL_SECONDS`. Once Phase 2 lands, this worker iterates tenants (`set_worker_context()` extended the same way as request-time RLS context) rather than running once globally.

**Implementation status (code-level, verified locally)**:
- `app/services/recommendations_scheduler.py` (new): `run_once()` lists every tenant (`select(Tenant.id)`), and for each one builds a `ProcessAnalysisRequest` from that tenant's *actual* ready source systems (via `source_inventory()`) rather than the manual button's fixed `["telegram", "email"]` default — a tenant with e-invoice or spreadsheet data gets analyzed on those too, with no one around to click a button and pick them. Tenants with zero ready content are skipped outright. `main()` follows the exact `rotation_runner.py` shape: heartbeat write, `run_once()`, `sleep(RECOMMENDATIONS_ANALYSIS_INTERVAL_SECONDS)`, forever, only if `RECOMMENDATIONS_AUTO_ANALYSIS_ENABLED=true`. Wired into `docker/entrypoint.sh` and surfaced on `/status` alongside the other three workers (`app/services/health.py`'s heartbeat key list, `app/routes/health.py`'s row builder).
- **A real, pre-existing bug was found and fixed while wiring this up**: `set_worker_context()` (`db.py`) built its RLS-context dict without a `tenant_id` key at all — a gap introduced during Phase 2's audit-chain work, when `_restore_rls_context`'s `after_begin` listener query was extended to always reference `:tenant_id`, but the worker-context builder wasn't updated to match. This wouldn't have surfaced in any test (SQLite no-ops the whole function) or even in the *existing* vault-rotation worker's common path — it only breaks the moment a worker's session opens a **second** transaction after a `db.commit()`, which `rotate_if_due()` does internally. It would have failed the first time vault rotation ran an actual rotation against the live database post-migration. Fixed by always including `tenant_id` (empty string, which `finbrain_tenant_id()` treats as NULL, when the work is genuinely tenant-less) and adding a regression test (`test_worker_context_carries_every_key_the_after_begin_listener_needs` in `test_database_portability.py`) that would have caught it.
- `set_worker_context()` also gained an `actor_ref` parameter (previously hardcoded to `"vault-rotation-worker"` for every caller, including this new one) and a `tenant_id` parameter, both keyword-only with defaults that preserve the three existing call sites' behavior unchanged.
- **A second real gap found**: `process_recommendations`/`recommendation_evidence` had RLS policies and table grants for `finbrain_app` only — the manual button's role. A background worker calling the identical `analyze_processes()` function would have been rejected outright. New migration `202608190009_worker_recommendations_access.sql` grants `finbrain_worker` unrestricted RLS (`using (true)`) on both tables, mirroring the existing `tokenized_content`/`token_vault` worker-access pattern — the real tenant boundary is the explicit `tenant_id` filter already in the Python service layer, not RLS, for worker-role writes. `recommendation_decisions` is deliberately left untouched: the scheduler only ever proposes, never approves/rejects/implements.
- New tests in `tests/test_recommendations_scheduler.py` seed two tenants (one with enough recurring evidence to produce a recommendation, one with ready content but not enough of it) and assert `run_once()` only creates a recommendation for the qualifying tenant, plus a tenant with zero ready content is skipped without error.

129/129 backend tests passing, ruff clean. Committed (`d7975a1`).

## Phase 6 — Entity resolution (customer/account identity)

New `customers` table as the canonical identity every source can link to. Generalize the deterministic name-normalization already built and proven for e-invoice supplier name-variants (`_normalize_name()` in `einvoice_readiness.py` — uppercase + strip corporate suffixes) into a shared matching pass run across all sources, not just invoices. Document embedding-similarity-based fuzzy matching as the natural next step, not built now — the deterministic pass is the right-sized first cut.

**Implementation status (code-level, verified locally) — scope narrowed from "all sources" to e-invoice buyers, with the reason recorded**: researching this phase surfaced that "every source can link to" isn't actually achievable as a first cut, and the plan's own framing ("the deterministic pass is the right-sized first cut") already anticipated narrowing it — here's the concrete reason. `einvoice_records.supplier_name`/`buyer_name` are the *only* structured, plaintext business-name columns anywhere in the schema. Every other source's customer/person identity lives inside `tokenized_content.content_text` behind a PERSON_/ORG_ token, deliberately unreadable without going through the disclosure/detokenization pipeline. Resolving *those* to a canonical customer would mean either inventing a new deterministic customer-scoped token type (so the token itself carries identity, mirroring the tenant-scoping fix from Phase 2) or running an authorized detokenization pass over ingested content — either one a real, separate design decision on its own, not a same-session extension of this one. So Phase 6 as built covers e-invoice buyer identity specifically; cross-source resolution is the documented next step, not silently dropped.

Also corrected a misreading while scoping this: `supplier_name` is the tenant's own issuing business (its consistency check in `_classify()` is about the tenant's own name hygiene for MyInvois, unrelated to customer identity); `buyer_name` is the actual counterparty being invoiced — the real "customer" this phase resolves.

- `app/services/entity_resolution.py` (new): `normalize_business_name()` (moved out of `einvoice_readiness.py`'s private `_normalize_name()`, now shared) and `resolve_customer(db, tenant_id, name)` — find-or-create, tenant-scoped, returns `None` for a name that normalizes to nothing usable (blank, or entirely punctuation/corporate-suffix boilerplate) rather than creating a garbage collision-prone row.
- New `Customer` model (`tenant_id`, `canonical_name`, `normalized_name`, unique per `(tenant_id, normalized_name)`) and `EInvoiceRecord.buyer_customer_id` FK, migration `202608190010_customers_entity_resolution.sql` (tenant-scoped RLS, `finbrain_app` only — nothing worker-facing needs this table yet).
- `create_record()` resolves-or-creates the buyer's `Customer` row and links it; `record_response()` and `EInvoiceRecordResponse` expose `buyer_customer_id`. `einvoice_readiness.py`'s own supplier-name-variant grouping (unrelated to customer identity, used for the tenant's-own-name-consistency readiness check) now reuses the same shared `normalize_business_name()` instead of a second private copy of the same logic.
- No new UI surface — the plan describes this as "foundational for future CRM work," not a deliverable feature on its own, so scope stopped at the data model, the resolution function, and exposing the FK through the existing e-invoice API/TypeScript type (`buyer_customer_id` added to `frontend/src/api/client.ts`'s `EInvoiceRecordResponse`) for a future page to build on.
- New tests in `tests/test_entity_resolution.py`: name normalization collapses casing/punctuation/suffix variants to the same key; `resolve_customer()` finds an existing row across name variants, stays isolated per tenant, and returns `None` for a name with nothing left after normalizing; `create_record()` links two records with buyer-name variants to the same customer and leaves `buyer_customer_id` null when no buyer name is given.

135/135 backend tests passing, ruff clean. Frontend `tsc -b` passes.

## Phase 7 — PDPA data-subject-rights endpoints

The existing architecture makes this cheaper than a typical PDPA implementation: every piece of PII in the system is already isolated behind an opaque token in `token_vault` — no other table ever stores raw PII. That means **erasure doesn't require hunting down every mention of a person across every table** — it means crypto-shredding the vault entry for a given token (destroying the decryption key, or overwriting `encrypted_value`) makes it permanently unrecoverable everywhere that token is referenced, in one operation. Scoping "erase everything about person X" cleanly needs Phase 6's identity resolution (to know which tokens belong to which person); a narrower `POST /privacy/erase-token/{token}` (erase one specific PII value) doesn't.

## Phase 8 — External audit-chain anchoring

Lightweight, pragmatic version: a scheduled job writes the current chain tail hash (`workflow_audit_log`/`audit_log`'s latest `event_hash`) to a destination the app's own Postgres credentials cannot write to — a separate minimal-permission storage bucket is enough to make silent tampering detectable (a rewritten chain would no longer match the last externally-anchored hash). Full RFC 3161 timestamping is the gold-standard alternative, noted but not recommended as the first cut — the cost/complexity isn't justified until the lightweight version proves the concept matters to a real auditor.

## Verification

- **Phase 1**: CI workflow itself is the verification — open a throwaway PR, confirm all four jobs (backend test/lint, frontend typecheck/lint/build) run and pass.
- **Phase 2**: two fake tenants in the test suite, one entity per tenant per table category (a conversation, a recommendation, an einvoice record), assert a principal from tenant A never sees tenant B's rows — both via a direct Postgres RLS check (manual, against the staging project) and via the SQLAlchemy-level test suite. Re-run the full existing 122-test suite to confirm nothing regresses.
- **Phase 3**: ask the same SEMANTIC-intent question against a seeded dataset before/after the change and confirm citations become similarity-ranked (not just occurred_at-ordered) and that ANALYZE_ALL/COUNT_RECORDS/LIST_RECORDS behavior is provably unchanged (existing tests for those intents should pass untouched).
- **Phase 4**: trigger a deliberate error locally, confirm it surfaces in Sentry; kill the DB connection locally, confirm `/health` now reports unhealthy instead of a static `ok`.
- **Phase 5**: run the worker locally with a short interval, confirm `process_recommendations` rows appear without any manual "Analyze Processes" click.
- **Phase 6/7/8**: covered per-phase when scoped in detail — each is small enough to verify with a handful of targeted tests once implemented.

This plan is intentionally sequenced so each phase is independently shippable and independently verifiable — nothing here requires committing to the whole roadmap up front. Phase 1 and Phase 3 are the two lowest-risk, highest-leverage places to start.
