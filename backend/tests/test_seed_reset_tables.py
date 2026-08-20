from seed.seed_data import RESET_TABLES


def test_reset_includes_new_foreign_key_dependents_before_their_parents():
    positions = {name: index for index, name in enumerate(RESET_TABLES)}
    dependencies = {
        "email_reply_correlations": ("email_ingestion_receipts", "outreach_actions"),
        "outreach_evidence": ("outreach_actions", "tokenized_content"),
        "outreach_actions": ("customer_endpoints", "customers"),
        "customer_endpoints": ("customers",),
        "customer_attention_signals": (
            "customer_attention_snapshots", "einvoice_records", "tokenized_content"
        ),
        "customer_attention_snapshots": ("customers",),
        "customer_record_links": ("customer_aliases", "customers", "tokenized_content"),
        "customer_aliases": ("customers",),
        "conversations": ("customers",),
        "email_ingestion_receipts": ("outreach_actions", "customers"),
        "einvoice_records": ("customers",),
    }
    for child, parents in dependencies.items():
        assert child in positions
        for parent in parents:
            assert parent in positions
            assert positions[child] < positions[parent]
