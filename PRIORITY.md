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
Structured CSV ingestion
  -> protected chat context
  -> functional frontend file upload
  -> demonstration SQL filters
  -> persona presentation
  -> final reliability pass
```

If time is severely limited, complete structured CSV ingestion, protected chat context, and the
final reliability rehearsal first.
