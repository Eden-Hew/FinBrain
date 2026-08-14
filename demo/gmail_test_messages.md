# Synthetic Gmail test messages

Send these messages to the Gmail inbox configured in `backend/.env`. Keep them unread until the
first FinBrain synchronization. All names, addresses, invoices, and amounts below are fictitious.

## Message 1: approval delay

Subject:

```text
[FINBRAIN DEMO] Approval required for DEMO-INV-2001
```

Body:

```text
SYNTHETIC DEMONSTRATION RECORD

Demo Customer Bravo requested an update on invoice DEMO-INV-2001.
The RM 6,200 payment is waiting for manager approval. No approval owner is assigned.
Finance should respond today.
```

## Message 2: refund without an owner

Subject:

```text
[FINBRAIN DEMO] Refund request DEMO-REF-2002
```

Body:

```text
SYNTHETIC DEMONSTRATION RECORD

Fictional customer Demo Customer Charlie requested a duplicate-payment refund of RM 780.
The request has no assigned finance owner. Contact demo.charlie@example.com for the synthetic test.
```

## Message 3: recurring approval problem

Subject:

```text
[FINBRAIN DEMO] Repeated approval queue delay
```

Body:

```text
SYNTHETIC DEMONSTRATION RECORD

A third fictional payment is waiting for manual approval after two follow-ups.
The operations team recommends a standardized approval queue and a named daily reviewer.
```

Optionally attach `demo/invoice_register.csv` to this message. The current Gmail connector adds
the extracted attachment text to the protected parent email record. It does not split an email CSV
attachment into `spreadsheet/invoice_row` records. Use direct protected file upload to test the
structured row-by-row CSV path.
