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
    print("RLS: enabled and forced")
    print("Supabase database check passed.")


if __name__ == "__main__":
    main()
