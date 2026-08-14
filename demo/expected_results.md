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

The exact total for email and Telegram records depends on the connector fixtures ingested before
the judging run. Verify those counts with SQL-first questions and the Supabase table view rather
than hard-coding them here.
