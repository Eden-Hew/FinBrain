# FinBrain end-to-end testing guide

This guide exercises the current proof of concept from protected ingestion through SQL-first
querying, conversation context, role-aware disclosure, recommendations, and audit verification.
All committed fixtures are synthetic.

## Test assets

| File | Test purpose |
| --- | --- |
| `demo/chat_upload_invoice_register.csv` | Chat-side structured CSV preview, row ingestion, and idempotency |
| `demo/invoice_register.csv` | Gmail attachment fixture; flattened into its parent email record |
| `demo/invoice_register_invalid.csv` | Duplicate-row and malformed-value validation failures |
| `demo/customer_followup.txt` | Generic text-document upload |
| `demo/sample_approval_email.eml` | EML extraction through protected file upload |
| `demo/gmail_test_messages.md` | Copy/paste messages for the live unread Gmail connector |
| `demo/judging_questions.md` | Suggested SQL, analytical, and contextual questions |
| `demo/expected_results.md` | Stable expected behavior and fixture counts |

## 1. One-time prerequisites

From the repository root in PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& .\.venv\Scripts\Activate.ps1
```

Confirm that the root environment is active and remove any unintended nested environment before
using uv from `backend`:

```powershell
python -c "import sys; print(sys.executable)"
Test-Path -LiteralPath '.\backend\.venv'
```

The interpreter should be `FinBrainOs\.venv\Scripts\python.exe`. If the second command is `True`,
stop all FinBrain processes and remove only that nested environment:

```powershell
Remove-Item -LiteralPath '.\backend\.venv' -Recurse -Force
```

Ensure `backend/.env` contains non-empty values for:

```text
TOKEN_ROOT_SECRET
DATABASE_URL
MORPHEUS_API_KEY
GEMINI_API_KEY
```

For live Gmail and Telegram tests, also configure their connector values as described in
`README.md`. Never paste their values into this guide or terminal screenshots.

## 2. Apply and verify the database schema

The structured-ingestion and conversation tables require the two latest Supabase migrations.
Review pending migrations, then apply them from the repository root:

```powershell
npx.cmd supabase migration list
npx.cmd supabase db push
```

Verify the complete schema without printing credentials:

```powershell
Set-Location backend
uv run --active --no-sync python -m scripts.check_supabase
Set-Location ..
```

Expected additions include:

```text
structured_ingestion_batches
conversations
conversation_turns
conversation_turn_citations
```

## 3. Run the automated gate

The full preparation command performs connectivity checks, prewarms GLiNER, runs backend tests and
Ruff, builds the frontend, and validates existing protected demo data. It does not reset Supabase:

```powershell
& .\scripts\prepare_demo.ps1
```

For a code-only rehearsal without network calls or model prewarming:

```powershell
& .\scripts\prepare_demo.ps1 -SkipNetworkChecks -SkipDetector
```

Expected code gate:

- All backend tests pass.
- Ruff reports no errors.
- Frontend lint has no errors; existing Fast Refresh warnings are non-blocking.
- The frontend production build succeeds.

## 4. Optional clean demonstration seed

This step deletes existing FinBrain application rows from the configured database. Do it only when
you intentionally want a clean demonstration dataset:

```powershell
Set-Location backend
uv run --active --no-sync python -m seed.seed_data --reset --yes
uv run --active --no-sync python -m scripts.check_demo_data
Set-Location ..
```

When live Gmail is the authoritative email fixture, omit the three built-in email seed records so
mailbox counts remain exact:

```powershell
Set-Location backend
uv run --active --no-sync python -m seed.seed_data --reset --yes --exclude-source email
Set-Location ..
```

Do not run the reset when testing against data you need to preserve.

## 5. Start and check the application

```powershell
& .\scripts\run_demo.ps1
& .\scripts\check_demo.ps1
```

Open:

- Frontend: <http://127.0.0.1:5173>
- API documentation: <http://127.0.0.1:8000/docs>

The health check should report the backend and frontend healthy. Gmail and Telegram are optional
only when they are disabled. Startup diagnostics are written to ignored `.runtime/logs` files.

## 6. Test structured CSV upload

1. Open **AI Agents** or **Protected Ingestion**.
2. Select the **General employee** demo persona.
3. Choose `demo/chat_upload_invoice_register.csv` using the paperclip or protected file control.
4. Wait for the protected preview.
5. Confirm the preview shows:
   - schema `invoice_register_v1`;
   - four valid rows;
   - zero invalid rows;
   - protected customer and amount tokens rather than raw values.
6. Select **Protect and ingest**.

Expected commit result:

- Four protected rows.
- Four ready rows when model services are available.
- Source system `spreadsheet`.
- Record type `invoice_row`.
- One independently citable record for each invoice.

Ask:

```text
How many spreadsheet invoices are pending approval?
List pending approval spreadsheet invoices without an owner.
Summarize all spreadsheet invoices.
```

Stable fixture facts:

- Four invoice rows total.
- Two have status `pending_approval`.
- One is `overdue`.
- One is `refund_requested`.
- Two have no assigned owner.

### Idempotency test

Upload and commit the unchanged CSV a second time. The result must still contain four spreadsheet
invoice records, not eight. Stable invoice HMAC identities update the same business rows.

To test refresh behavior, copy the fixture outside the repository, change the amount or status for
`CHAT-INV-4001`, then preview and commit the copy. The source record ID should remain stable while
the protected fingerprint, tokens, summary, and embedding refresh.

### Validation test

Upload `demo/invoice_register_invalid.csv`. It intentionally contains a duplicate `invoice_id`,
an invalid amount, and an invalid date. The fixture contains three input rows, but only the first
row is valid. Preview should return row-numbered safe validation codes without echoing rejected
customer or amount values, and it must not silently treat the malformed CSV as a generic document.

## 7. Test generic document and EML upload

Upload and commit each file separately:

```text
demo/customer_followup.txt
demo/sample_approval_email.eml
```

Expected behavior:

- Preview performs extraction and tokenization without creating a database record.
- Commit re-reads the file and verifies the preview HMAC.
- Each file creates one `document_upload` source.
- Phone numbers, email addresses, names detected by GLiNER, and amounts are protected before model
  summarization or embedding.
- The original filename is not stored as operational metadata.

You can also test a text-based PDF or DOCX. Encrypted PDFs, invalid signatures, scanned documents
without extractable text, and unsupported extensions should return a safe error code.

## 8. Test live unread Gmail ingestion

Confirm this configuration shape in `backend/.env`:

```dotenv
EMAIL_CONNECTOR_ENABLED=true
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_IMAP_PORT=993
EMAIL_IMAP_USERNAME=your.demo.inbox@gmail.com
EMAIL_IMAP_PASSWORD=your-16-character-gmail-app-password
EMAIL_IMAP_FOLDER=INBOX
EMAIL_IMAP_USE_SSL=true
EMAIL_INCLUDE_ATTACHMENTS=true
```

Replace the two placeholder values locally. Use the Gmail address as the username and a Google app
password, not the normal account password. The real values must not be printed, committed, or
included in screenshots.

### Connectivity-only check

This opens the configured folder read-only and does not fetch or ingest messages:

```powershell
Set-Location backend
uv run --active --no-sync python -m scripts.check_email
Set-Location ..
```

### Ingestion test

1. Copy the three synthetic messages from `demo/gmail_test_messages.md` into new emails sent to the
   configured Gmail inbox.
2. Leave them unread.
3. Optionally attach `demo/invoice_register.csv` to the third message.
4. Open **Protected Ingestion** and select **Sync now**, or allow the email worker to poll.
5. Inspect the Email capture panel.

Expected behavior:

- Only unread messages newer than the durable UID cursor are considered.
- The mailbox is opened read-only; FinBrain does not mark Gmail messages read.
- Each delivery creates an HMAC receipt and at most one `email` protected record.
- Re-running **Sync now** does not duplicate previously receipted messages.
- Supported attachment text is protected as part of the parent email record.
- Unsupported attachments do not prevent supported email body ingestion.

Important current boundary: a CSV attached to Gmail is extracted into the parent email record. It
is not currently split into structured `spreadsheet/invoice_row` records. Direct browser upload is
the authoritative structured CSV test.

Useful questions after ingesting the three messages:

```text
How many email records are ready?
List all email records.
Summarize all email approval delays.
Which email records have no assigned owner?
```

## 9. Test Telegram protected ingestion

The configured Telegram account must be listed in `TELEGRAM_OPERATOR_ROLES`. In the private bot
chat:

1. Send `/whoami` to verify the numeric operator identity.
2. Send this synthetic text:

```text
SYNTHETIC DEMONSTRATION RECORD
Demo Customer Delta reports that RM 8,400 for DEMO-INV-3001 is awaiting manager approval.
Finance should assign an owner today.
```

3. Inspect the protected preview.
4. Confirm ingestion.
5. Send the same text again and confirm that the bot's receipt/idempotency behavior is safe.

Ask in the web chat:

```text
List all Telegram records.
Summarize Telegram records that still need action.
```

## 10. Test SQL-first filters

Use these questions exactly:

```text
How many high-priority payment approval delays came from email this week?
List overdue spreadsheet invoices without an owner.
Summarize support tickets from the last 7 days.
```

Verify:

- Count and list answers use `structured-filter` mode when appropriate.
- Generic `CSV` means directly uploaded `spreadsheet` rows; use `bank CSV` for seeded bank
  transactions.
- Exact counts do not cite an arbitrary top-five result set.
- Analytical questions send every SQL-eligible protected record through bounded reasoning batches.
- Empty result sets report insufficient evidence without calling the external reasoning model.

## 11. Test protected conversation context

Start a new chat and run:

```text
Show me all email count.
Tell me what each of them means.
Describe each email.
About customer Charlie.
Tell me about the third one.
```

Verify:

- The first response creates an opaque conversation ID.
- A structured count keeps its matching record set as protected conversation context even though
  the count response intentionally displays zero citations.
- `them` resolves to all six email records behind that count.
- The Charlie turn cites one matching email.
- `the third one` skips the one-record Charlie turn and resolves against the nearest earlier result
  set that actually has a third citation.
- The indicator increases to `Context: 5 protected turns`.
- Current citations are remapped to the current `SOURCE-n` identifiers.
- **New chat** clears messages, chips, and conversation context.

The database stores protected questions, protected answers, query plans, and citation foreign keys
only. It must never store the authorized plaintext answer shown in the browser.

## 12. Test role-aware amount disclosure

1. Select **General employee**.
2. Ask:

```text
Tell me about CHAT-INV-4001.
```

3. General employee should see an amount band rather than the exact amount.
4. Select **Finance operator**.
5. On the answer, select **Re-run as selected persona**.
6. Finance operator should see the normalized authorized amount `RM 4,500`.
7. The earlier General employee answer must not be silently rewritten.

Use **Show model view** to confirm that the external model saw a token similar to
`AMOUNT_BAND_3_<opaque>`, never the exact amount.

## 13. Test recommendation permissions and workflow

Open **Approvals** and test each persona:

| Persona | View recommendations | Analyze | Approve/reject/implement |
| --- | --- | --- | --- |
| General employee | No | No | No |
| Finance operator | Yes | No | No |
| Compliance reviewer | Yes | No | No |
| Owner / director | Yes | Yes | Yes |

As Owner / director:

1. Select **Analyze recurring problems**.
2. Inspect the protected evidence from more than one source.
3. Approve the recommendation.
4. Mark it implemented.

Unauthorized personas should see disabled controls or a safe backend `403`; changing frontend
state must never bypass backend authorization.

## 14. Test disclosure and workflow audits

1. Complete the General employee and Finance operator comparison above.
2. Select **Compliance reviewer**.
3. Open **Audit**.
4. Select **Re-verify**.

Expected behavior:

- Disclosure chain is valid.
- Workflow chain is valid.
- Authorized and denied token attempts appear as separate audit events.
- Recommendation analysis and decisions appear in the workflow chain.
- Non-compliance personas cannot open the live audit endpoints.

## 15. Verify directly in Supabase

Use **Supabase Dashboard → Table Editor** for protected rows. Never expose or edit token-vault
ciphertext during a demonstration.

Useful SQL Editor queries:

```sql
select source_system, record_type, processing_status, count(*)
from public.tokenized_content
group by source_system, record_type, processing_status
order by source_system, record_type, processing_status;

select source_record_id, safe_metadata->>'status' as status,
       safe_metadata->>'has_assigned_owner' as has_owner,
       processing_status
from public.tokenized_content
where source_system = 'spreadsheet'
order by source_record_id;

select batch_ref, schema_name, status, total_rows, valid_rows,
       protected_rows, ready_rows, failed_rows
from public.structured_ingestion_batches
order by created_at desc;

select c.id, c.status, count(t.id) as turns
from public.conversations c
left join public.conversation_turns t on t.conversation_id = c.id
group by c.id, c.status
order by max(c.updated_at) desc;

select source_system, count(*)
from public.tokenized_content
where processing_status = 'ready'
group by source_system
order by source_system;
```

The `content_text`, `summary`, and conversation text columns should contain protected tokens, not
raw email addresses, phone numbers, customer names detected by GLiNER, or exact monetary values.

## 16. Shutdown and restart test

```powershell
& .\scripts\check_demo.ps1
& .\scripts\stop_demo.ps1
& .\scripts\run_demo.ps1
& .\scripts\check_demo.ps1
& .\scripts\stop_demo.ps1
```

Expected behavior:

- Start succeeds with free ports.
- Required components report healthy.
- Stop validates recorded PID ownership and descendants.
- Ports 8000 and 5173 are free after stopping.
- A second start succeeds without stale frontend or backend processes.

## Troubleshooting

### `Failed to fetch`

Run `scripts/check_demo.ps1`. Confirm the frontend URL matches the configured API origin and inspect
`.runtime/logs/backend.stderr.log` without sharing secrets.

### Upload returns a missing-table error

Apply `202608140001_structured_ingestion.sql` and
`202608140002_conversation_context.sql` using `npx.cmd supabase db push`, then rerun
`scripts.check_supabase`.

### Gmail finds no messages

- Confirm the messages are unread.
- Confirm they have UIDs newer than the stored cursor.
- Send a new synthetic message rather than toggling an old message behind the cursor back to unread.
- Run `python -m scripts.check_email` from the active project environment.

### Telegram stays unavailable

Confirm `python-telegram-bot` is installed through the backend project dependencies, the bot token
is configured, and the numeric operator ID is allowlisted.

### GLiNER is slow on first start

Run `scripts/prepare_demo.ps1` before judging. It prewarms the detector. CPU is the portable
default; this workstation may set `GLINER_DEVICE=cuda` while preserving its compatible global
Torch installation.
