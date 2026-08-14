# FinBrain Hackathon Priorities

This document defines the remaining work that provides the highest demonstration value for the
Track 2 problem statement. The focus is a complete, reliable proof of concept—not production
infrastructure.

## Objective

Demonstrate one coherent journey:

```text
Gmail + Telegram + structured CSV + uploaded document
  -> unified protected ingestion
  -> plain-language questions
  -> SQL-authoritative scope
  -> protected cross-source analysis with citations
  -> contextual follow-up
  -> role-aware disclosure
  -> evidence-backed process recommendation
  -> human approval
  -> verifiable audit trail
```

## Priority 1: Structured CSV ingestion

FinBrain currently extracts CSV attachments as text. For the hackathon, implement one or two
allowlisted business schemas rather than attempting arbitrary spreadsheet support.

Recommended invoice schema:

```csv
invoice_id,customer,amount,status,assigned_owner,due_date
```

Required behavior:

- Parse and validate headers and row shapes.
- Create one protected canonical record per logical row.
- Preserve an opaque parent attachment or batch reference.
- Tokenize sensitive cells such as customer names and monetary values.
- Retain safe structured fields such as status and date for SQL filtering.
- Produce stable row-level source IDs and citations.
- Prevent repeated ingestion of the same attachment rows.
- Report invalid, unsupported, and skipped rows without storing raw values.

Target questions:

- `How many invoices are awaiting approval?`
- `Summarize overdue invoices from the CSV.`
- `Which invoice has no assigned owner?`
- `Compare the spreadsheet records with related emails.`

## Priority 2: Protected chat context

Add short, persistent, citation-aware conversation context.

Required behavior:

- Generate and return a conversation ID.
- Store tokenized questions and protected model answers only.
- Store the citation-to-record mapping for each turn.
- Include a bounded recent history, initially four to six turns.
- Resolve references such as `those`, `it`, and `the second one` against prior citations.
- Re-evaluate authorization on every request instead of inheriting an earlier role.
- Never store a detokenized user-facing answer.
- Add a **New conversation** control to the frontend.
- Add conversation expiration and deletion suitable for the demonstration.

Target conversation:

```text
Summarize all approval-delay records.
Which of those came from email?
Which one has the largest amount?
Who needs to follow up on it?
```

Long-term memory and unrestricted conversation history are out of scope.

## Priority 3: Functional frontend file upload

Replace the visual-only chat attachment control with a real protected ingestion flow.

Reuse the existing in-memory extractors for:

- TXT
- Markdown
- CSV
- EML
- Text-based PDF
- DOCX

Required behavior:

- Upload the file to FastAPI using bounded request limits.
- Extract content in memory without persisting raw bytes.
- Convert extracted content into the canonical ingestion contract.
- Display a protected preview before confirmation.
- Show protection and enrichment status after submission.
- Preserve document, page, attachment, or row provenance where applicable.
- Clearly report unsupported files, encrypted PDFs, and extraction failures.

OCR for scanned images and scanned PDFs remains deferred.

## Priority 4: Expand deterministic SQL filters

Extend the current allowlisted query planner only for fields needed in the demonstration:

- Source system
- Date and date range
- Record type
- Structured-summary category
- Priority
- `action_required`
- Structured CSV status
- Structured CSV assigned owner

Target question:

```text
How many high-priority payment approval delays came from email this week?
```

Morpheus must not generate or execute SQL. The backend should continue translating recognized
intents and filters into parameterized SQLAlchemy queries.

## Priority 5: Polish the permission demonstration

Full authentication is deferred, but the role-aware behavior must be clear and honest.

Use fixed demonstration personas:

| Persona | Role | Demonstrated access |
| --- | --- | --- |
| General employee | `general_employee` | Safe contact access and approximate monetary bands |
| Finance operator | `finance_ops` | Exact operational amounts and finance contacts |
| Compliance officer | `compliance` | Restricted compliance values and audit visibility |
| Business owner | `owner_director` | Recommendations and decision controls |

The UI must label these identities as demonstration personas and state that authentication is not
implemented. During judging, show the same answer under at least two personas to make the
role-dependent disclosure visible.

## Priority 6: Demonstration reliability

Complete a reliability pass before adding lower-value features.

Checklist:

- Confirm `scripts/run_demo.ps1`, `scripts/check_demo.ps1`, and `scripts/stop_demo.ps1` manage every
  local process reliably.
- Prewarm GLiNER before judging.
- Verify Morpheus, Gemini, Supabase, Telegram, and Gmail connectivity.
- Reset and verify the clean Supabase demonstration dataset.
- Prepare one relevant unread Gmail message.
- Prepare one Telegram capture.
- Prepare one structured invoice CSV.
- Rehearse every planned question and follow-up.
- Confirm citations, role disclosure, recommendations, and both audit chains.
- Keep a recorded fallback demonstration in case a remote dependency is unavailable.
- Avoid account creation, model downloads, migration, or dependency installation during judging.

## Recommended judging flow

1. Upload an invoice CSV containing several approval records.
2. Ingest a related unread Gmail message.
3. Capture a related customer complaint through Telegram.
4. Show protected records from all three sources in FinBrain and Supabase.
5. Ask: `How many approval-delay records are there across all sources?`
6. Ask: `Summarize them and cite every source.`
7. Follow up: `Which of those has the largest amount and no assigned owner?`
8. Switch from general employee to finance operator and compare banded versus exact amounts.
9. Generate a recurring-process recommendation.
10. Approve the recommendation using the owner persona.
11. Open the audit workspace and verify the disclosure and workflow chains.

This flow directly demonstrates:

```text
scattered business knowledge
  -> one protected knowledge layer
  -> trustworthy natural-language answers
  -> role-aware access
  -> actionable process improvement
```

## Explicitly deferred until after the hackathon

- Full Supabase Auth and verified JWT roles
- Multi-tenant organization isolation
- WhatsApp Business integration
- Live banking and accounting APIs
- Google Drive, OneDrive, and SharePoint OAuth
- Arbitrary spreadsheet schemas
- OCR
- Production key rotation and vault re-encryption
- Production RLS/JWT architecture
- Large-scale vector-retrieval tuning
- Kubernetes or complex cloud infrastructure
- Automated task-system integrations
- Full production monitoring, incident response, and compliance review

## Recommended implementation order

```text
Structured CSV core
  -> CSV preview and commit upload
  -> protected chat context
  -> general document upload
  -> demonstration SQL filters
  -> persona presentation
  -> final reliability pass
```

If time is severely limited, complete structured CSV ingestion with its upload path, protected chat
context, and the final reliability rehearsal first.

---

## Implementation blueprint

The sections above describe product priority. This blueprint defines how to implement the work in
the current repository without weakening the existing privacy boundary.

### Baseline

The plan assumes the following current state:

- `CanonicalIngestionRecord` is the only source-neutral ingestion contract.
- `protect_canonical_record()` persists protected content before external enrichment.
- `enrich_protected_record()` receives protected content only.
- `TokenizedContent.safe_metadata` is portable JSON on SQLite and JSONB on Postgres.
- `/query` uses deterministic source planning and sends every SQL-eligible ready record to the
  protected reasoning layer.
- More than 20 analytical records are already processed through protected batching.
- Query answers have validated `SOURCE-n` citations and role-gated detokenization.
- The frontend file control currently stores only a filename chip.
- The baseline verification target is 54 passing backend tests plus frontend lint and build.

### Non-negotiable implementation rules

Every work package must preserve these invariants:

1. Raw file bytes, raw questions, raw extracted text, and detokenized answers must not be stored in
   the database, application logs, exception messages, or retry state.
2. External reasoning and embedding providers receive protected content only.
3. Source IDs, batch IDs, mailbox references, and conversation references must be opaque.
4. Idempotency identifiers derived from source content must use HMAC with `TOKEN_ROOT_SECRET`, not
   an unkeyed digest.
5. Morpheus must never generate or execute SQL. Only an allowlisted backend plan may produce
   parameterized SQLAlchemy statements.
6. Every schema change must be delivered through a forward-only Supabase migration. SQLite model
   creation must remain compatible with the same SQLAlchemy models.
7. No frontend-only permission check is considered an authorization boundary. Backend checks must
   remain authoritative even while identities are demonstration roles.
8. New prompts must preserve protected tokens and validate citations, unknown tokens, and residual
   recognizable PII.
9. All file and conversation operations must have explicit size, row, turn, and lifetime bounds.
10. Each work package must be independently testable and leave the existing demonstration usable.

## Architecture decisions

| Decision | Hackathon choice | Reason |
| --- | --- | --- |
| CSV scope | `invoice_register_v1` allowlisted schema | Enables reliable SQL questions without building a generic ETL product |
| CSV record granularity | One `TokenizedContent` row per invoice row | Gives row-level citations, updates, and counts |
| CSV source system | `spreadsheet` | Keeps transport separate from business provenance |
| File preview | Protect on preview; re-upload and verify digest on commit | Avoids persisting raw drafts while preserving confirmation |
| Upload transport | Bounded raw request body with filename/type metadata | Avoids multipart temporary-file behavior and accepts one file at a time |
| Conversation history | Last six protected turns | Sufficient for the demo and bounded for prompts |
| Follow-up resolution | Prior citation IDs plus deterministic reference detection | Prevents the model from guessing what `those` or `it` means |
| Conversation storage | Protected question, protected answer, plan, and citation mapping only | Supports context without retaining authorized plaintext |
| Query filtering | Shared SQLAlchemy eligibility builder | Prevents count/list/analysis paths from disagreeing |
| Persona model | Four fixed, clearly labeled demonstration personas | Makes access behavior visible without pretending authentication exists |
| Large analysis | Existing protected batches of 20 | Preserves complete evidence without one oversized request |

## Dependency and delivery order

```text
Phase 0: baseline and migration preparation
  |
  +-> Phase 1: structured CSV domain service
  |      |
  |      +-> Phase 2: protected file preview and commit UI
  |
  +-> Phase 3: protected conversation context
         |
         +-> Phase 4: shared SQL filter planner
                    |
                    +-> Phase 5: persona demonstration polish
                               |
                               +-> Phase 6: reliability and rehearsal
```

The product priority remains CSV first and chat context second. The file-upload transport is
implemented immediately after the CSV core because it is how judges will submit the structured
file. Chat context can be developed independently once its migration is defined.

## Phase 0: Baseline and migration preparation

### Tasks

1. Confirm a clean branch based on `main` and record the baseline commit.
2. Run the current backend tests, Ruff, frontend lint, and frontend build.
3. Run `scripts.check_supabase` and save only non-sensitive schema/count output.
4. Confirm the clean seed reset is reproducible before introducing new tables.
5. Reserve two forward-only migrations:
   - `202608140001_structured_ingestion.sql`
   - `202608140002_conversation_context.sql`
6. Add the new tables to `scripts.check_supabase` and the reset ordering in `seed.seed_data` only
   when their corresponding models exist.

### Exit criteria

- Existing 54 tests pass before feature work.
- Supabase migration history is synchronized.
- No secrets, local databases, model caches, or runtime logs are staged.

## Phase 1: Structured CSV ingestion

### 1.1 Supported schema

Implement one required schema named `invoice_register_v1`:

```csv
invoice_id,customer,amount,status,assigned_owner,due_date
```

Column rules:

| Column | Validation | Protected representation |
| --- | --- | --- |
| `invoice_id` | Required, unique in the file, bounded identifier | Included in protected row text; used only through HMAC for source identity |
| `customer` | Required, non-empty, bounded text | Detected and tokenized as sensitive content |
| `amount` | Required MYR value with at most two decimals | Reversible amount token in text plus safe `amount_band` metadata |
| `status` | Required allowlisted business status | Normalized safe metadata |
| `assigned_owner` | Optional bounded text | Tokenized when present; safe `has_assigned_owner` metadata |
| `due_date` | Required ISO date | Normalized safe metadata |

Initial normalized statuses:

```text
pending_approval
overdue
paid
refund_requested
cancelled
unknown
```

Accept common header aliases only through an explicit mapping, for example `invoice` to
`invoice_id` and `owner` to `assigned_owner`. Reject duplicate normalized headers and unknown
required layouts rather than guessing.

### 1.2 Parser and limits

Create:

```text
backend/app/integrations/structured_csv/__init__.py
backend/app/integrations/structured_csv/schemas.py
backend/app/integrations/structured_csv/parser.py
backend/app/integrations/structured_csv/adapter.py
backend/app/integrations/structured_csv/service.py
```

Parser requirements:

- Use Python's `csv` module; do not parse rows with string splitting.
- Accept UTF-8 with optional BOM and Windows-1252 fallback.
- Detect comma, semicolon, or tab only within a bounded sample.
- Maximum file size: 10 MB.
- Maximum rows: 500 for the hackathon.
- Maximum columns: 20.
- Maximum cell length: 4,000 characters.
- Reject NUL bytes, duplicate invoice IDs, missing required headers, malformed dates, and malformed
  amounts.
- Normalize line endings and trim surrounding whitespace without altering meaningful internal
  text.
- Return row-numbered validation codes without including raw cell values.
- Never include a rejected row's content in an exception or log message.

### 1.3 Stable identity and idempotency

Use two HMAC identifiers:

- `batch_ref`: HMAC of the complete file bytes and schema name.
- `row_ref`: HMAC of the normalized invoice ID and schema name.

Create source IDs in this form:

```text
spreadsheet:invoice:<row_ref-prefix>
```

Using the invoice identity rather than row position means a corrected spreadsheet refreshes the
same business record. `ingest_canonical_record()` already detects changed content through its
keyed fingerprint and refreshes the protected row.

### 1.4 Canonical row mapping

Each valid row becomes a `CanonicalIngestionRecord`:

```json
{
  "source_record_id": "spreadsheet:invoice:<opaque-row-ref>",
  "source_system": "spreadsheet",
  "record_type": "invoice_row",
  "text": "Invoice ID: INV-1024\nCustomer: ...\nAmount: RM 4500\nStatus: pending approval\nAssigned owner: ...\nDue date: 2026-08-20",
  "occurred_at": null,
  "metadata": {
    "schema_name": "invoice_register_v1",
    "batch_ref": "<opaque-batch-ref>",
    "row_number": "2",
    "status": "pending_approval",
    "due_date": "2026-08-20",
    "has_assigned_owner": "false",
    "amount_band": "3",
    "origin_channel": "web_upload"
  }
}
```

Exact customer, owner, and monetary values must appear only in the canonical text or metadata that
passes through the normal protection boundary. Safe derived fields may be stored only after their
derivation is deterministic and documented.

### 1.5 Batch status model

Add `StructuredIngestionBatch` to `backend/app/models.py` and create it in
`202608140001_structured_ingestion.sql`.

Minimum columns:

```text
batch_ref              text primary key
schema_name            text not null
origin_channel         text not null
status                 text not null
total_rows             integer not null
valid_rows             integer not null
failed_rows            integer not null
protected_rows         integer not null
ready_rows             integer not null
failure_code           text null
created_at             timestamptz not null
updated_at             timestamptz not null
```

Allowed statuses:

```text
validated
protecting
enriching
ready
partial
failed
```

The table must contain no raw filename, raw header, raw cell, or external identity. Enable and
force RLS, revoke Data API access, and add a status/created-time index.

Do not create a separate row-receipt table initially. Stable row source IDs plus the existing
content fingerprint already provide row idempotency. Add a receipt table later only if partial
retry requirements prove that it is necessary.

### 1.6 Protection and enrichment order

For a batch:

1. Parse and validate the complete CSV.
2. Create or load the opaque batch status row.
3. Call `protect_canonical_record()` for every valid row before any external model call.
4. Commit protected rows and update `protected_rows`.
5. Enrich protected rows sequentially through `enrich_protected_record()`.
6. Update ready/failed counts without storing provider exception text.
7. Return a batch result with row source IDs, protected status, and validation codes.

This order ensures a provider outage cannot cause raw spreadsheet rows to be lost or placed in a
retry queue.

### 1.7 API contracts

Add response schemas:

```text
StructuredCsvPreviewResponse
StructuredCsvCommitResponse
StructuredCsvRowResult
StructuredCsvValidationIssue
```

The preview response should expose:

```json
{
  "preview_digest": "<opaque-hmac>",
  "schema_name": "invoice_register_v1",
  "total_rows": 4,
  "valid_rows": 4,
  "invalid_rows": 0,
  "protected_preview": [
    {
      "row_number": 2,
      "content_text": "Invoice ID: INV-1024 ... AMOUNT_BAND_3_..."
    }
  ],
  "issues": []
}
```

The commit response should expose the batch status and row-level protected/enrichment status, but
never return raw rows.

### 1.8 Tests

Add:

```text
backend/tests/test_structured_csv.py
backend/tests/test_structured_csv_route.py
```

Required cases:

- Valid UTF-8 and BOM input.
- Windows-1252 fallback.
- Header alias normalization.
- Duplicate or missing headers.
- Duplicate invoice IDs.
- Malformed date and amount.
- Row, column, cell, and file limits.
- Stable batch and row HMAC references.
- Same invoice updates the same protected record.
- Exact names and amounts absent from protected content and batch status.
- Row-level amount token and vault entry created.
- Batch protection completes before enrichment begins.
- Failed enrichment retains protected rows.
- SQLite and Postgres-compatible model types.

### 1.9 Acceptance criteria

- Calling the structured CSV service with the prepared fixture creates one ready protected record
  per valid invoice; the browser upload path is added in Phase 2.
- Reprocessing the unchanged file creates no duplicate rows.
- Changing INV-1024 refreshes the same opaque source record.
- Direct database and batch-status counts agree for pending invoices. Natural-language status
  filtering is connected in Phase 4.
- Every row is independently retrievable and can become a row-level citation.
- No raw customer or amount value is found in `tokenized_content`, batch status, logs, or errors.

## Phase 2: Protected file preview and commit

This phase first exposes structured CSV upload, then generalizes the same transport to existing
document extractors.

### 2.1 Backend transport

Create:

```text
backend/app/routes/uploads.py
backend/app/services/upload_ingestion.py
backend/tests/test_upload_ingestion.py
backend/tests/test_upload_routes.py
```

Add the router in `backend/app/main.py`.

Use one bounded binary request body per call rather than accepting an arbitrary multipart bundle.
Pass request metadata in validated `X-FinBrain-*` headers so a potentially identifying filename is
not written into the URL or the default access log:

```text
X-FinBrain-Filename
X-FinBrain-Record-Type
X-FinBrain-Role
X-FinBrain-Preview-Digest on commit
```

Endpoints:

```text
POST /uploads/preview
POST /uploads/commit
```

Both endpoints receive the file again. The browser retains the selected `File` between preview and
commit. The backend recalculates the HMAC digest during commit and rejects a mismatch. This avoids
persisting a raw server-side upload draft.

Read request data in bounded chunks and abort immediately when the configured maximum is exceeded.
Do not write uploaded bytes to a temporary path. Scrub filenames before including them in protected
source text and never store the original filename as operational metadata.

### 2.2 Preview behavior

Preview must:

1. Validate extension, MIME type, signature, and size.
2. Extract content with the existing TXT, Markdown, CSV, EML, PDF, and DOCX extractors.
3. Run protection without external enrichment.
4. Return a bounded protected preview and opaque digest.
5. Discard the raw bytes and extracted plaintext when the request ends.

Extract a side-effect-free protection-preview helper from the ingestion service rather than
opening a database transaction and rolling it back. The helper may return protected text and
ephemeral encrypted vault-entry objects, but preview must discard those objects after constructing
the response. Commit runs the authoritative protection path again and persists newly generated
vault ciphertext.

For CSV, dispatch to the structured parser when the schema matches `invoice_register_v1`.
Otherwise return an explicit `unsupported_csv_schema` result instead of silently flattening it.

### 2.3 Commit behavior

Commit must:

1. Re-read and revalidate the uploaded bytes.
2. Compare the HMAC against `preview_digest` using a constant-time comparison.
3. Dispatch structured CSV to the batch service.
4. Dispatch other supported documents to a single canonical `document_upload` record.
5. Derive the document source ID from a purpose-bound HMAC of the file digest, never the filename.
6. Protect and persist before enrichment.
7. Return protected content, record IDs, status, and extraction warnings.

Use `source_system=spreadsheet` for structured CSV rows and `source_system=document_upload` for
general uploaded documents.

### 2.4 Frontend experience

Update:

```text
frontend/src/api/client.ts
frontend/src/screens/Agents.tsx
frontend/src/screens/Ingestion.tsx
frontend/src/styles.css or the existing relevant stylesheet
```

Replace the filename-only chip with these states:

```text
selected -> previewing -> protected preview -> committing -> protected/ready/failed
```

The preview panel must show:

- File type and size.
- Recognized schema for CSV.
- Valid and invalid row counts.
- Protected excerpt or protected row samples.
- Extraction warnings.
- **Protect and ingest** and **Cancel** actions.

Do not place raw file contents in React state after the browser `File` reference is no longer
needed. Revoke any object URL and clear the file input after commit or cancellation.

### 2.5 Gmail structured-attachment integration

Treat Gmail CSV splitting as an extension after direct upload is working:

1. Replace the current attachment string list with a typed `EmailAttachmentExtraction` result.
2. Keep unsupported attachment status separate from the parent body.
3. For a recognized invoice CSV, ingest structured rows through the same CSV batch service with
   `origin_channel=email` and an opaque parent email reference.
4. Keep the parent email as its own record and insert only a protected marker describing the
   separately ingested attachment.
5. Add an email attachment/batch association if the frontend must navigate from the email to its
   rows. Do not overload the current single `EmailIngestionReceipt.source_record_id` field with a
   list.

This extension is not required to demonstrate direct structured upload, but it should be completed
if Gmail attachments are part of the final judging script.

### 2.6 Acceptance criteria

- The frontend attachment control performs real preview and ingestion.
- Raw bytes are not written to the repository, database, runtime directory, or logs.
- A modified file cannot be committed with an earlier preview digest.
- A PDF, DOCX, and invoice CSV each create protected content through the canonical service.
- Unsupported or encrypted files display a clear safe error.
- The newly ingested source is immediately available to `/query` after enrichment.

## Phase 3: Protected conversation context

### 3.1 Database design

Add these models and migration objects in `202608140002_conversation_context.sql`.

#### `conversations`

```text
id                  text primary key
status              text not null
created_at          timestamptz not null
updated_at          timestamptz not null
expires_at          timestamptz not null
```

Allowed status values: `active`, `expired`, and `deleted`.

#### `conversation_turns`

```text
id                    bigint identity primary key
conversation_id       text references conversations(id) on delete cascade
sequence_number       integer not null
user_role             text not null
protected_question    text not null
protected_answer      text not null
query_intent          text not null
source_systems        jsonb not null
reasoning_mode        text not null
insufficient_evidence boolean not null
created_at            timestamptz not null
unique (conversation_id, sequence_number)
```

#### `conversation_turn_citations`

```text
id                    bigint identity primary key
turn_id               bigint references conversation_turns(id) on delete cascade
ordinal               integer not null
tokenized_content_id  bigint references tokenized_content(id) on delete restrict
unique (turn_id, ordinal)
unique (turn_id, tokenized_content_id)
```

Enable and force RLS, revoke Data API access, and add indexes for conversation sequence and expiry.

Do not store the raw user question, authorized final answer, external user identity, or copied
source excerpts in conversation tables. Citations reference the canonical protected records.

### 3.2 API changes

Extend `QueryRequest`:

```json
{
  "question": "Which of those came from email?",
  "role": "general_employee",
  "conversation_id": "optional-opaque-id"
}
```

Extend `QueryResponse`:

```json
{
  "conversation_id": "opaque-id",
  "turn_id": 12
}
```

If no conversation ID is supplied, `/query` creates one. Add:

```text
POST   /conversations
GET    /conversations/{conversation_id}
DELETE /conversations/{conversation_id}
```

`GET` returns protected turns only and is for restoring the current demonstration session. Delete
should mark the conversation deleted and remove its turns in the same transaction for the current
single-user proof of concept.

### 3.3 Conversation service

Create:

```text
backend/app/services/conversations.py
backend/app/routes/conversations.py
backend/tests/test_conversations.py
backend/tests/test_conversation_routes.py
```

Responsibilities:

- Create opaque UUID conversation IDs.
- Load at most the latest six active protected turns.
- Refresh `updated_at` and a 24-hour `expires_at` on each turn.
- Expire old conversations lazily when accessed and through an optional cleanup function.
- Store each turn only after a protected answer and validated citation set exist.
- Persist the protected answer before role-gated detokenization.
- Never serialize a detokenized answer into conversation state.

### 3.4 Follow-up resolution

Add deterministic referential detection for terms such as:

```text
those
these
them
it
that record
the first one
the second one
the previous result
```

When detected:

1. Load the prior turn's ordered citation mappings.
2. Use those `tokenized_content_id` values as the candidate set.
3. Apply any newly recognized source/date/type/category filters as an intersection.
4. Reissue the surviving records as the current turn's `SOURCE-n` identifiers.
5. Include a short protected history block for linguistic continuity.

Do not pass stale `SOURCE-n` labels from prior answers into the new model prompt. Prior source IDs
must be remapped for the current turn so citations always refer to the current response contract.

For ordinal references, map `first`, `second`, and numeric forms to the prior citation order in the
backend. Return insufficient evidence when the referenced position does not exist.

### 3.5 Privacy and role switching

- Store the selected role for audit context, but authorize each turn from the current request.
- A later finance role may reveal more from the newly generated protected answer, but it must not
  cause an earlier detokenized response to be stored or replayed.
- A role change in the frontend should clearly affect the next turn only.
- Add **Re-run as this persona** if the demo needs to compare the same protected answer across
  roles; do not silently rewrite old chat bubbles.
- Query-side vault entries remain governed by existing token ACLs and disclosure auditing.

### 3.6 Reasoning prompt

Pass history in a bounded protected form:

```text
Protected conversation history:
[TURN-1 USER] ...
[TURN-1 ASSISTANT] ...
[TURN-2 USER] ...
[TURN-2 ASSISTANT] ...

Current protected evidence:
[SOURCE-1] ...
```

The prompt must state that conversation text is context, while only current `SOURCE-n` blocks are
citable evidence. Model output validation remains unchanged for citations and protected tokens.

### 3.7 Frontend changes

Update the API client and Agents screen to:

- Hold the current `conversation_id`.
- Send it with every question after the first response.
- Add a visible **New conversation** action.
- Reset messages, chips, and conversation state together.
- Restore protected turns only when explicitly requested.
- Keep the scripted fallback outside persisted conversation state.
- Display a small `Context: N protected turns` indicator.

### 3.8 Tests

Required cases:

- First query creates a conversation.
- Subsequent query appends the next sequence number.
- Stored questions and answers contain no recognizable PII.
- Detokenized output is never stored.
- Only six turns are included in the reasoning prompt.
- `those` restricts candidates to prior citations.
- `the second one` selects the correct prior citation.
- A new email filter intersects prior citations.
- Invalid, expired, and deleted conversation IDs are safely rejected.
- Switching roles does not reuse prior authorization.
- Current citations are remapped and validated.
- Deleting a conversation removes turns and citation mappings.

### 3.9 Acceptance criteria

This exact flow must work:

```text
Summarize all approval-delay records.
Which of those came from email?
Which one has the largest visible amount band?
Who needs to follow up on it?
```

Use demonstration amounts in distinct bands. The model cannot compare exact values hidden inside
two tokens from the same band; exact encrypted-value aggregation is explicitly outside this phase.

## Phase 4: Shared deterministic SQL filters

### 4.1 Refactor the plan

Extend `QueryPlan` with a typed filter object:

```text
source_systems
record_types
occurred_from
occurred_to
categories
priorities
action_required
content_ids
metadata_equals
metadata_missing
```

Create one shared eligibility builder, for example:

```text
backend/app/services/query_filters.py
```

It should return a SQLAlchemy `Select[TokenizedContent]` used by:

- Count records.
- List records.
- Complete analytical selection.
- Conversation citation intersections.

The current source inventory may remain a separate grouped query, but filtered record counts must
not be derived from the unfiltered inventory.

### 4.2 Initial language rules

Implement deterministic recognition for:

- `today`, `yesterday`, `this week`, `last week`, `this month`, and `last N days`.
- Record words such as invoice, email, Telegram message, meeting note, support ticket, and
  spreadsheet row.
- Priority values `low`, `medium`, and `high`.
- Action phrases such as `needs action`, `action required`, and `no action required`.
- Known structured-summary categories present in the demo dataset.
- Spreadsheet status values and `without an owner` / `unassigned`.

Add an explicit application timezone setting, defaulting to `Asia/Kuala_Lumpur`, and convert date
boundaries to UTC before SQL filtering.

### 4.3 JSON portability

Use SQLAlchemy JSON expressions supported by both SQLite JSON and Postgres JSONB. If one expression
cannot be portable, isolate the dialect-specific implementation behind the same function and test
both generated paths.

Only allowlisted metadata keys may enter a query expression:

```text
status
due_date
has_assigned_owner
amount_band
schema_name
batch_ref
```

Never interpolate a question-derived key, operator, or SQL fragment.

### 4.4 Exact and analytical execution

- Counts, grouped counts, and listings should return backend-formatted exact answers without a
  model call.
- Analytical questions should pass every filtered ready record into the existing protected batch
  reasoning service.
- If the result set is empty, return explicit insufficient evidence without calling Morpheus.
- Include normalized plan/filter information in server-side debug output only when it contains no
  raw question content or sensitive values.

### 4.5 Tests and acceptance criteria

Add table-driven planner tests and route tests for:

```text
How many high-priority payment approval delays came from email this week?
List overdue spreadsheet invoices without an owner.
Summarize support tickets from the last 7 days.
Which of those Telegram records still needs action?
```

Verify the same eligible IDs are used by count, listing, and analysis for an equivalent filter.

## Phase 5: Demonstration personas

### 5.1 Frontend role cleanup

Replace the current indirect mapping (`finance_director`, `employee`, and `guest`) with role values
that match the backend exactly:

```text
general_employee
finance_ops
compliance
owner_director
```

Create one shared persona configuration containing label, description, backend role, and visible
capabilities. Use it in chat, ingestion, recommendations, and audit views.

### 5.2 Remove hardcoded action roles

The current API client submits hardcoded owner/compliance roles for recommendation and audit
operations. Change these functions to accept the active persona role and let backend authorization
return 403 when the persona lacks access.

The frontend should:

- Hide or disable unauthorized actions with an explanation.
- Still handle backend 403 responses safely.
- Label the selector **Demo persona**.
- Display `Authentication is not implemented` near the selector.
- Avoid calling compliance users `Guest`, which currently misrepresents their access.

### 5.3 Comparison interaction

Add a **Re-run as persona** action to an answer. It should submit the same raw question as a new
turn under the newly selected role and create a new disclosure audit trail. Do not detokenize
protected content in the browser.

Recommended judging comparison:

1. General employee asks about INV-1024 and sees an amount band.
2. Finance operator re-runs the question and sees the exact normalized amount.
3. Compliance opens the disclosure audit and verifies both attempts.
4. Owner/director opens the recommendation workflow and makes a decision.

### 5.4 Tests and acceptance criteria

- Every frontend action sends the selected backend role.
- General employee cannot open audit or recommendation decision endpoints.
- Finance can view recommendations but cannot decide them.
- Compliance can view audit chains but cannot decide recommendations.
- Owner/director can analyze and decide recommendations.
- The UI contains an explicit demonstration-authentication disclaimer.

## Phase 6: Reliability and judging preparation

### 6.1 Process lifecycle scripts

Harden the existing PowerShell scripts:

- `run_demo.ps1` must clean up already-started processes if a later start or readiness check fails.
- Record child process IDs or validated process ancestry when Python launchers create child
  interpreters.
- `stop_demo.ps1` must stop validated descendants before their tracked parent and verify ports 8000
  and 5173 are free afterward.
- Never stop a PID whose start time or ancestry no longer matches the recorded process.
- Write privacy-safe stdout/stderr to `.runtime/logs` for diagnosis.
- `check_demo.ps1` should report each component independently and return a nonzero exit code if a
  required component is unhealthy.
- Telegram and email should be treated as optional when their configuration is disabled.

### 6.2 Preparation script

Add `scripts/prepare_demo.ps1` that performs only safe, explicit preparation:

1. Confirm `.venv`, frontend dependencies, and ignored `backend/.env` exist.
2. Confirm required environment values are present without printing them.
3. Prewarm GLiNER using `backend/scripts/prewarm_detector.py`.
4. Verify Gemini, Supabase, and Telegram connectivity using existing checkers.
5. Verify Gmail only when enabled.
6. Run backend tests and the frontend build.
7. Run `scripts.check_demo_data` after an explicitly separate reset/seed step.
8. Confirm ports are free before launch.

Do not make the preparation script reset Supabase implicitly. Database reset remains a separate,
visible destructive command requiring `--yes`.

### 6.3 Synthetic demonstration assets

Add non-sensitive fixtures:

```text
demo/invoice_register.csv
demo/customer_followup.txt
demo/judging_questions.md
demo/expected_results.md
```

All identities and financial values must be clearly fictitious. Expected results should describe
counts, source systems, and role behavior without embedding API keys, mailbox details, Telegram
IDs, database URLs, or exact generated token hashes.

### 6.4 Final acceptance rehearsal

Run the judging flow twice from a clean reset and verify:

- Every connector and upload creates the expected number of protected records.
- SQL counts match Supabase counts.
- Every analytical answer uses the expected eligible record count.
- Every displayed citation resolves to a protected source record.
- General and finance amount views differ as expected.
- The recommendation contains evidence from more than one source.
- Approval and implementation events produce a valid workflow chain.
- Disclosure attempts produce a valid disclosure chain.
- Start, health check, stop, and second start all succeed without stale processes.

Record one complete successful run as a fallback, but keep the live path as the primary
demonstration.

## Cross-feature API summary

Planned API changes:

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/uploads/preview` | Extract and protect a bounded file without persistence |
| `POST` | `/uploads/commit` | Revalidate and ingest the confirmed file |
| `POST` | `/query` | Add optional conversation ID and return turn identity |
| `POST` | `/conversations` | Explicitly start a protected conversation |
| `GET` | `/conversations/{id}` | Restore protected recent turns |
| `DELETE` | `/conversations/{id}` | Delete the demonstration conversation |
| `GET` | `/structured-ingestion-batches/{batch_ref}` | Return safe batch progress and counts |

Do not add a general SQL endpoint, raw file download endpoint, vault-value endpoint, or raw
conversation export endpoint.

## Migration summary

### `202608140001_structured_ingestion.sql`

- Create `structured_ingestion_batches`.
- Add constraints and status index.
- Enable and force RLS.
- Revoke `anon` and `authenticated` Data API grants.

### `202608140002_conversation_context.sql`

- Create `conversations`, `conversation_turns`, and `conversation_turn_citations`.
- Add cascade/restrict foreign keys and sequence uniqueness.
- Add expiry and turn-order indexes.
- Enable and force RLS on all three tables.
- Revoke `anon` and `authenticated` Data API grants.

Update `backend/scripts/check_supabase.py`, `backend/scripts/check_demo_data.py`, and the seed reset
table order after each migration. Reset child tables before their parents.

## Test matrix

| Boundary | Minimum verification |
| --- | --- |
| CSV parser | Schema, encoding, limits, row errors, stable IDs |
| CSV privacy | No raw PII in protected rows, batches, errors, or logs |
| Upload | Size/type/signature checks, preview digest, no persistence before commit |
| Ingestion | Protect-all-before-enrich, idempotency, safe retries |
| Conversations | Protected storage, six-turn bound, expiry, deletion |
| Follow-ups | Citation intersection, ordinal resolution, role recheck |
| SQL planner | Date/type/category/priority/metadata filters and portability |
| Reasoning | All eligible evidence, batching, valid citations and tokens |
| Personas | Correct role propagation and backend denial handling |
| Scripts | Clean start, health, stop, restart, and failure cleanup |
| Supabase | Migration history, RLS, grants, indexes, expected tables |
| Frontend | Upload states, new conversation, persona labels, production build |

## Suggested commit sequence

Keep changes reviewable and independently reversible:

```text
feat: add protected structured CSV ingestion
feat: add confirmed file upload workflow
feat: add protected citation-aware conversations
feat: expand deterministic SQL query filters
feat: add explicit hackathon demo personas
chore: harden local demo lifecycle and fixtures
docs: update setup and judging runbook
```

Apply and verify each migration before merging the feature that depends on it.

## Effort and cut line

Relative implementation effort:

| Work package | Effort | Demo value | Required for final flow |
| --- | --- | --- | --- |
| Structured CSV core | Large | Very high | Yes |
| CSV upload preview/commit | Medium | Very high | Yes |
| Protected conversation context | Large | Very high | Yes |
| General document upload | Medium | High | Preferred |
| SQL filter expansion | Medium | High | Preferred |
| Persona cleanup | Small | High | Yes |
| Reliability and rehearsal | Medium | Critical | Yes |
| Gmail CSV attachment splitting | Medium | Medium | Optional if direct upload is shown |

If the schedule slips, cut work in this order:

1. Defer Gmail-specific CSV splitting; keep direct CSV upload.
2. Limit general upload to CSV, TXT, and text-based PDF.
3. Limit SQL expansion to date, priority, action-required, status, and missing owner.
4. Keep conversation history to the latest four turns instead of six.

Do not cut:

- Protected CSV row ingestion.
- Citation-aware follow-up mapping.
- Role re-evaluation per turn.
- Backend permission checks.
- Demo lifecycle verification.
- Privacy and residual-PII tests.

## Overall definition of done

The hackathon implementation is complete when a clean environment can execute the recommended
judging flow and all of the following are true:

1. Gmail, Telegram, and structured CSV contribute protected records to one database.
2. A direct uploaded document is processed through the canonical privacy boundary.
3. SQL returns authoritative counts for the same rows used in analysis.
4. A follow-up question resolves only against the previous cited records.
5. Morpheus receives protected content and returns valid current-turn citations.
6. General and finance personas receive visibly different authorized amount views.
7. A multi-source recurring problem becomes a persisted recommendation.
8. An owner decision is recorded in the workflow audit chain.
9. Disclosure and workflow chains both verify successfully.
10. Supabase contains no recognizable raw PII in protected content, summaries, batch status, or
    conversation history.
11. The complete backend suite, Ruff, frontend lint, and frontend build pass.
12. The demo can start, stop, and restart cleanly without stale listeners or manual process cleanup.
