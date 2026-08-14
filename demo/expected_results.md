# Expected demonstration results

These expectations intentionally omit generated token hashes and environment-specific identifiers.

- Upload preview recognizes `invoice_register_v1`, with four valid rows and no invalid rows.
- Commit creates four independently citable `spreadsheet` / `invoice_row` protected records.
- Re-uploading the unchanged file does not duplicate invoice records.
- The fixture contains two `pending_approval` invoices, one `overdue` invoice, and one
  `refund_requested` invoice.
- Two invoices have no assigned owner.
- General employee sees a protected amount band for CHAT-INV-4001.
- Finance operator sees the authorized normalized value `RM 4,500` after a fresh query.
- Compliance reviewer can verify the disclosure and workflow hash chains.
- Owner / director can generate, approve, and mark a cross-source recommendation implemented.
- Conversation follow-ups remain limited to the preceding cited protected records.
- Suggested prompt buttons submit through the same live query route as typed questions.
- Semantic answers report `morpheus` or `gemini` when an external provider succeeds;
  `offline-demo` is visibly reported when the fallback is used.
- Exact counts and simple listings report `structured-filter` and do not claim an external AI call.
- Citations resolve to the protected records stored for that exact turn; unknown citation IDs are
  rejected.
- Audit displays separate disclosure and workflow counts, visible query references and entry
  hashes, and independently valid chains.

The exact total for email and Telegram records depends on the connector fixtures ingested before
the judging run. Verify those counts with SQL-first questions and the Supabase table view rather
than hard-coding them here.
