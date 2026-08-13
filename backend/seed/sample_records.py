SAMPLE_RECORDS = [
    {
        "source_record_id": "demo:email:001",
        "source_system": "email",
        "record_type": "customer_email",
        "occurred_at": "2026-08-04T09:15:00+08:00",
        "text": (
            "Subject: Payment approval delay for INV-260804-17\n"
            "Internal category: payment_approval_delay. Nur Aisyah from Meranti Trading says "
            "the RM4,850 invoice is still pending manager approval after two follow-ups. "
            "Contact nur.aisyah@example.com or 012-345 6789. Finance must respond today."
        ),
        "metadata": {"channel": "inbox", "business_unit": "finance_ops"},
    },
    {
        "source_record_id": "demo:email:002",
        "source_system": "email",
        "record_type": "customer_email",
        "occurred_at": "2026-08-06T14:20:00+08:00",
        "text": (
            "Subject: Second escalation on approval queue\n"
            "Internal category: payment_approval_delay. Daniel Lee at Bintang Supplies reports "
            "that invoice INV-260731-09 for RM7,200 has waited four days for an assigned approver. "
            "Reply to daniel.lee@example.com before close of business."
        ),
        "metadata": {"channel": "inbox", "business_unit": "finance_ops"},
    },
    {
        "source_record_id": "demo:email:003",
        "source_system": "email",
        "record_type": "customer_email",
        "occurred_at": "2026-08-10T11:05:00+08:00",
        "text": (
            "Subject: Refund status requested\n"
            "Customer Priya Nair asked when the RM380 duplicate-payment refund will be completed. "
            "The request has no owner. Contact 016-882 1402 and assign a finance representative."
        ),
        "metadata": {"channel": "inbox", "business_unit": "customer_care"},
    },
    {
        "source_record_id": "demo:telegram:001",
        "source_system": "telegram",
        "record_type": "customer_message",
        "occurred_at": "2026-08-05T10:40:00+08:00",
        "text": (
            "Internal category: payment_approval_delay. Ahmad Faizal says payment for "
            "INV-260802-11, RM2,950, remains blocked because no manager owns the approval. "
            "He has followed up twice at 013-772 4108 and needs an update today."
        ),
        "metadata": {"channel": "private_chat", "business_unit": "finance_ops"},
    },
    {
        "source_record_id": "demo:telegram:002",
        "source_system": "telegram",
        "record_type": "customer_message",
        "occurred_at": "2026-08-08T16:10:00+08:00",
        "text": (
            "Internal category: payment_approval_delay. Siti Aminah reports invoice "
            "INV-260805-23 for RM12,300 is still in the manual approval queue with no response. "
            "Please escalate and update siti.aminah@example.com."
        ),
        "metadata": {"channel": "private_chat", "business_unit": "finance_ops"},
    },
    {
        "source_record_id": "demo:telegram:003",
        "source_system": "telegram",
        "record_type": "customer_message",
        "occurred_at": "2026-08-11T13:25:00+08:00",
        "text": (
            "Customer Wong Mei Ling reports that shipment SO-8831 arrived with two damaged units. "
            "She requested replacement confirmation at 017-440 9912 before Friday."
        ),
        "metadata": {"channel": "private_chat", "business_unit": "fulfilment"},
    },
    {
        "source_record_id": "demo:crm:001",
        "source_system": "crm",
        "record_type": "case_note",
        "occurred_at": "2026-08-07T09:30:00+08:00",
        "text": (
            "Internal category: payment_approval_delay. Case C-1042 for customer Farah Ismail "
            "shows three contacts about invoice INV-260729-05. The RM6,100 payment approval "
            "remains unassigned. Next action: finance manager review within one business day."
        ),
        "metadata": {"case_queue": "accounts_receivable", "business_unit": "finance_ops"},
    },
    {
        "source_record_id": "demo:crm:002",
        "source_system": "crm",
        "record_type": "case_note",
        "occurred_at": "2026-08-09T15:45:00+08:00",
        "text": (
            "Case C-1058: Lim Chee Kean requested cancellation after receiving the wrong product. "
            "The return pickup is booked but no replacement owner is assigned. Email "
            "lim.ck@example.com with the resolution plan."
        ),
        "metadata": {"case_queue": "returns", "business_unit": "customer_care"},
    },
    {
        "source_record_id": "demo:bank_csv:001",
        "source_system": "bank_csv",
        "record_type": "transaction",
        "occurred_at": "2026-08-05T17:00:00+08:00",
        "text": (
            "Transaction date 2026-08-05; payer Meranti Trading; amount RM4,850; "
            "reference INV-260804-17; account 5643-0021-889; status received, awaiting allocation."
        ),
        "metadata": {"import_batch": "august_week_1", "business_unit": "finance_ops"},
    },
    {
        "source_record_id": "demo:bank_csv:002",
        "source_system": "bank_csv",
        "record_type": "transaction",
        "occurred_at": "2026-08-08T17:00:00+08:00",
        "text": (
            "Transaction date 2026-08-08; payer Bintang Supplies; amount RM7,200; "
            "reference INV-260731-09; account 1142 3390 5567; status unmatched."
        ),
        "metadata": {"import_batch": "august_week_2", "business_unit": "finance_ops"},
    },
    {
        "source_record_id": "demo:meeting:001",
        "source_system": "meeting_notes",
        "record_type": "operations_minutes",
        "occurred_at": "2026-08-12T09:00:00+08:00",
        "text": (
            "Weekly operations meeting: the team identified repeated payment approval delays "
            "across email, Telegram, and CRM. Three cases lacked a named approver. Action: define "
            "an approval owner and review the unresolved queue daily."
        ),
        "metadata": {"meeting": "weekly_operations", "business_unit": "operations"},
    },
    {
        "source_record_id": "demo:support:001",
        "source_system": "support_ticket",
        "record_type": "ticket",
        "occurred_at": "2026-08-12T14:35:00+08:00",
        "text": (
            "Ticket T-2207: customer Hafiz Rahman cannot download the paid invoice receipt from "
            "the portal. Account email hafiz.rahman@example.com. Support reproduced the issue and "
            "requested a portal fix within two days."
        ),
        "metadata": {"queue": "portal_support", "business_unit": "technology"},
    },
]
