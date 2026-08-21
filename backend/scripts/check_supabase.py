from sqlalchemy import text

from app.config import get_settings
from app.db import engine

REQUIRED_TABLES = (
    "tokenized_content",
    "protected_token_registry",
    "token_vault",
    "vault_key_versions",
    "vault_rotation_jobs",
    "audit_log",
    "telegram_update_receipts",
    "integration_status",
    "email_sync_state",
    "email_ingestion_receipts",
    "process_recommendations",
    "recommendation_evidence",
    "recommendation_decisions",
    "workflow_audit_log",
    "structured_ingestion_batches",
    "conversations",
    "conversation_turns",
    "conversation_turn_citations",
    "user_roles",
    "customers",
    "einvoice_records",
    "einvoice_outreach_drafts",
    "customer_aliases",
    "customer_record_links",
    "customer_attention_snapshots",
    "customer_attention_signals",
    "customer_endpoints",
    "customer_identity_claims",
    "outreach_actions",
    "outreach_evidence",
    "email_reply_correlations",
    "telegram_onboarding_sessions",
    "tenant_outreach_policies",
)
REQUIRED_INGESTION_COLUMNS = {
    "source_system",
    "occurred_at",
    "content_fingerprint",
    "safe_metadata",
    "structured_summary",
    "processing_status",
    "processing_error",
    "enrichment_mode",
    "updated_at",
}
REQUIRED_VAULT_COLUMNS = {
    "key_version",
    "masked_value",
    "encryption_algorithm",
}
REQUIRED_CURRENT_COLUMNS = {
    "customers": {
        "tenant_id", "canonical_name", "normalized_name", "profile_status",
        "identity_review_status", "profile_origin", "primary_name_token"
    },
    "customer_endpoints": {"origin", "delivery_token", "last_interaction_at"},
    "telegram_onboarding_sessions": {
        "tenant_id", "telegram_endpoint_token", "telegram_delivery_token", "name_token",
        "email_token", "phone_token", "customer_id", "profile_content_id", "status"
    },
    "telegram_update_receipts": {
        "tenant_id", "customer_id", "onboarding_session_id", "status"
    },
    "tenant_outreach_policies": {
        "tenant_id", "telegram_reminders_enabled", "grace_days", "repeat_interval_days",
        "max_reminders", "require_approval", "policy_version"
    },
    "customer_identity_claims": {
        "tenant_id", "customer_id", "endpoint_id", "identity_token", "claim_basis",
        "confidence", "evidence_content_id", "status", "occurrence_count"
    },
    "einvoice_records": {
        "tenant_id", "buyer_customer_id", "buyer_email_token", "buyer_phone_token",
        "due_date", "paid_at", "source_record_id"
    },
    "einvoice_outreach_drafts": {
        "tenant_id", "einvoice_record_id", "channel", "draft_text", "status"
    },
    "conversations": {"context_customer_id", "context_updated_at"},
    "customer_record_links": {
        "tenant_id", "customer_id", "tokenized_content_id", "alias_id", "match_basis"
    },
    "outreach_actions": {
        "tenant_id", "customer_id", "customer_endpoint_id", "protected_subject",
        "protected_body", "status", "provider_message_ref_hash", "replied_at",
        "origin_type", "origin_invoice_id", "scheduled_for", "created_by_actor_ref"
    },
    "email_ingestion_receipts": {
        "customer_id", "outreach_action_id", "in_reply_to_ref_hash",
        "correlation_status", "correlated_at"
    },
}


def main() -> None:
    settings = get_settings()
    if settings.database_backend != "postgresql":
        raise SystemExit(
            "DATABASE_URL is not PostgreSQL. Copy a Supabase connection URI into backend/.env."
        )

    with engine.connect() as connection:
        database, user, version = connection.execute(
            text("select current_database(), current_user, current_setting('server_version')")
        ).one()
        vector_version = connection.scalar(
            text("select extversion from pg_extension where extname = 'vector'")
        )
        tables = {
            name: connection.scalar(text("select to_regclass(:name)"), {"name": f"public.{name}"})
            for name in REQUIRED_TABLES
        }
        embedding_type = connection.scalar(
            text(
                "select format_type(a.atttypid, a.atttypmod) "
                "from pg_attribute a "
                "join pg_class c on c.oid = a.attrelid "
                "join pg_namespace n on n.oid = c.relnamespace "
                "where n.nspname = 'public' and c.relname = 'tokenized_content' "
                "and a.attname = 'embedding' and not a.attisdropped"
            )
        )
        ingestion_columns = {
            row.column_name: (row.data_type, row.is_nullable)
            for row in connection.execute(
                text(
                    "select column_name, data_type, is_nullable from information_schema.columns "
                    "where table_schema = 'public' and table_name = 'tokenized_content'"
                )
            )
        }
        role_list_type = connection.scalar(
            text(
                "select format_type(a.atttypid, a.atttypmod) "
                "from pg_attribute a "
                "join pg_class c on c.oid = a.attrelid "
                "join pg_namespace n on n.oid = c.relnamespace "
                "where n.nspname = 'public' and c.relname = 'token_vault' "
                "and a.attname = 'allowed_roles' and not a.attisdropped"
            )
        )
        vector_index = connection.scalar(
            text("select to_regclass('public.tokenized_content_embedding_idx')")
        )
        workflow_index = connection.scalar(
            text("select to_regclass('public.workflow_audit_created_idx')")
        )
        structured_batch_index = connection.scalar(
            text("select to_regclass('public.structured_ingestion_status_created_idx')")
        )
        conversation_expiry_index = connection.scalar(
            text("select to_regclass('public.conversation_expiry_idx')")
        )
        vault_columns = {
            row.column_name
            for row in connection.execute(
                text(
                    "select column_name from information_schema.columns "
                    "where table_schema = 'public' and table_name = 'token_vault'"
                )
            )
        }
        auth_hook = connection.scalar(
            text("select to_regprocedure('public.custom_access_token_hook(jsonb)')")
        )
        auth_columns = {
            (row.table_name, row.column_name)
            for row in connection.execute(
                text(
                    "select table_name, column_name from information_schema.columns "
                    "where table_schema = 'public' and ("
                    "(table_name = 'conversations' and column_name = 'created_by_user_id') or "
                    "(table_name = 'process_recommendations' "
                    "and column_name = 'created_by_user_id') or "
                    "(table_name = 'audit_log' and column_name = 'actor_ref'))"
                )
            )
        }
        rls_status = connection.execute(
            text(
                "select c.relname, c.relrowsecurity, c.relforcerowsecurity "
                "from pg_class c join pg_namespace n on n.oid = c.relnamespace "
                "where n.nspname = 'public' and c.relname = any(cast(:tables as text[]))"
            ),
            {"tables": list(REQUIRED_TABLES)},
        ).all()
        security_roles = {
            row.rolname: row.rolbypassrls
            for row in connection.execute(
                text(
                    "select rolname, rolbypassrls from pg_roles "
                    "where rolname in ('finbrain_app', 'finbrain_worker')"
                )
            )
        }
        append_only_triggers = {
            row.tgname
            for row in connection.execute(
                text(
                    "select tgname from pg_trigger where not tgisinternal "
                    "and tgname in ('audit_log_append_only', "
                    "'workflow_audit_log_append_only')"
                )
            )
        }
        vault_role_policy = connection.scalar(
            text(
                "select qual from pg_policies where schemaname = 'public' "
                "and tablename = 'token_vault' and policyname = 'finbrain_app_vault'"
            )
        )
        worker_einvoice_policy = connection.scalar(
            text(
                "select qual from pg_policies where schemaname = 'public' "
                "and tablename = 'einvoice_records' "
                "and policyname = 'finbrain_worker_einvoice_attention_read'"
            )
        )
        current_columns = {
            table: {
                row.column_name
                for row in connection.execute(
                    text(
                        "select column_name from information_schema.columns "
                        "where table_schema = 'public' and table_name = :table"
                    ),
                    {"table": table},
                )
            }
            for table in REQUIRED_CURRENT_COLUMNS
        }
        current_indexes = {
            name: connection.scalar(text("select to_regclass(:name)"), {"name": f"public.{name}"})
            for name in (
                "customers_tenant_idx",
                "einvoice_records_buyer_customer_idx",
                "einvoice_records_tenant_idx",
                "einvoice_outreach_drafts_tenant_idx",
                "customer_alias_lookup_idx",
                "customer_record_links_customer_idx",
                "customer_attention_latest_idx",
                "conversations_customer_context_idx",
                "customer_endpoints_customer_idx",
                "outreach_queue_idx",
                "email_reply_customer_idx",
                "customer_identity_claims_review_idx",
                "customer_endpoints_delivery_idx",
                "telegram_onboarding_tenant_status_idx",
                "telegram_receipts_tenant_status_idx",
                "einvoice_buyer_email_token_idx",
                "einvoice_buyer_phone_token_idx",
                "outreach_worker_queue_idx",
            )
        }
        customer_origin_checks = {
            row.conname: row.definition
            for row in connection.execute(
                text(
                    "select c.conname, pg_get_constraintdef(c.oid) as definition "
                    "from pg_constraint c "
                    "join pg_class t on t.oid = c.conrelid "
                    "join pg_namespace n on n.oid = t.relnamespace "
                    "where n.nspname = 'public' "
                    "and t.relname in ('customers', 'customer_endpoints') "
                    "and c.conname in ("
                    "'customers_profile_origin_check', "
                    "'customer_endpoints_origin_check')"
                )
            )
        }

    missing = [name for name, relation in tables.items() if relation is None]
    if vector_version is None:
        raise SystemExit("Connected, but the pgvector extension is not installed.")
    if missing:
        raise SystemExit(f"Connected, but migrations are missing tables: {', '.join(missing)}")
    if embedding_type != "vector(768)":
        raise SystemExit(f"Expected vector(768), found {embedding_type!r}.")
    missing_ingestion_columns = REQUIRED_INGESTION_COLUMNS - ingestion_columns.keys()
    if missing_ingestion_columns:
        raise SystemExit(
            "Unified-ingestion migration is missing columns: "
            + ", ".join(sorted(missing_ingestion_columns))
        )
    if ingestion_columns["safe_metadata"][0] != "jsonb":
        raise SystemExit("Expected safe_metadata jsonb.")
    if ingestion_columns["structured_summary"][0] != "jsonb":
        raise SystemExit("Expected structured_summary jsonb.")
    if ingestion_columns["embedding"][1] != "YES":
        raise SystemExit("Embedding must be nullable for retryable protected records.")
    if role_list_type != "jsonb":
        raise SystemExit(f"Expected allowed_roles jsonb, found {role_list_type!r}.")
    missing_vault_columns = REQUIRED_VAULT_COLUMNS - vault_columns
    if missing_vault_columns:
        raise SystemExit(
            "Versioned vault columns are missing: "
            + ", ".join(sorted(missing_vault_columns))
        )
    if vector_index is None:
        raise SystemExit("The HNSW embedding index is missing.")
    if workflow_index is None:
        raise SystemExit("The Track 2 recommendation migration is incomplete.")
    if structured_batch_index is None:
        raise SystemExit("The structured-ingestion migration is incomplete.")
    if conversation_expiry_index is None:
        raise SystemExit("The conversation-context migration is incomplete.")
    expected_auth_columns = {
        ("conversations", "created_by_user_id"),
        ("process_recommendations", "created_by_user_id"),
        ("audit_log", "actor_ref"),
    }
    if auth_hook is None or auth_columns != expected_auth_columns:
        raise SystemExit("The Supabase Auth/JWT migration is incomplete.")
    insecure_tables = [name for name, enabled, forced in rls_status if not enabled or not forced]
    if insecure_tables:
        raise SystemExit(f"RLS is not enabled and forced for: {', '.join(insecure_tables)}")
    if security_roles != {"finbrain_app": False, "finbrain_worker": False}:
        raise SystemExit("FinBrain database roles are missing or can bypass RLS.")
    if append_only_triggers != {
        "audit_log_append_only",
        "workflow_audit_log_append_only",
    }:
        raise SystemExit("Append-only audit triggers are missing.")
    if vault_role_policy is None or "allowed_roles" not in vault_role_policy:
        raise SystemExit("The token vault policy does not enforce allowed_roles.")
    if worker_einvoice_policy is None or "tenant_id" not in worker_einvoice_policy:
        raise SystemExit("The email worker lacks tenant-scoped invoice attention access.")
    for table, expected in REQUIRED_CURRENT_COLUMNS.items():
        if missing_columns := expected - current_columns[table]:
            raise SystemExit(
                f"Current product schema is missing {table} columns: "
                + ", ".join(sorted(missing_columns))
            )
    if missing_indexes := [name for name, value in current_indexes.items() if value is None]:
        raise SystemExit("Current product schema is missing indexes: " + ", ".join(missing_indexes))
    expected_origin_values = {
        "customers_profile_origin_check": ("manual", "einvoice", "email", "telegram"),
        "customer_endpoints_origin_check": (
            "manual", "inbound_email", "telegram_onboarding", "telegram_contact_share"
        ),
    }
    for constraint, expected_values in expected_origin_values.items():
        definition = customer_origin_checks.get(constraint, "")
        if any(f"'{value}'" not in definition for value in expected_values):
            raise SystemExit(
                f"Current product schema has an incompatible {constraint} constraint."
            )

    print(f"Database: {database}")
    print(f"Database user: {user}")
    print(f"Postgres: {version}")
    print(f"pgvector: {vector_version}")
    print(f"Tables: {', '.join(REQUIRED_TABLES)}")
    print(f"Embedding column: {embedding_type}")
    print("Unified ingestion columns: present")
    print(f"Role-list column: {role_list_type}")
    print("HNSW index: present")
    print("Track 2 recommendation schema: present")
    print("Structured ingestion schema: present")
    print("Protected conversation schema: present")
    print("Supabase Auth role and ownership schema: present")
    print("Versioned vault schema and role-enforced ciphertext RLS: present")
    print("Append-only audit triggers: present")
    print(
        "Email-first customer identity, attention, governed outreach, "
        "and reply correlation: present"
    )
    print("RLS: enabled and forced")
    print("Supabase database check passed.")


if __name__ == "__main__":
    main()
