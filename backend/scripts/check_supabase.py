from sqlalchemy import text

from app.config import get_settings
from app.db import engine

REQUIRED_TABLES = ("tokenized_content", "token_vault", "audit_log")


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
        rls_status = connection.execute(
            text(
                "select c.relname, c.relrowsecurity, c.relforcerowsecurity "
                "from pg_class c join pg_namespace n on n.oid = c.relnamespace "
                "where n.nspname = 'public' and c.relname = any(cast(:tables as text[]))"
            ),
            {"tables": list(REQUIRED_TABLES)},
        ).all()

    missing = [name for name, relation in tables.items() if relation is None]
    if vector_version is None:
        raise SystemExit("Connected, but the pgvector extension is not installed.")
    if missing:
        raise SystemExit(f"Connected, but migrations are missing tables: {', '.join(missing)}")
    if embedding_type != "vector(768)":
        raise SystemExit(f"Expected vector(768), found {embedding_type!r}.")
    if role_list_type != "jsonb":
        raise SystemExit(f"Expected allowed_roles jsonb, found {role_list_type!r}.")
    if vector_index is None:
        raise SystemExit("The HNSW embedding index is missing.")
    insecure_tables = [name for name, enabled, forced in rls_status if not enabled or not forced]
    if insecure_tables:
        raise SystemExit(f"RLS is not enabled and forced for: {', '.join(insecure_tables)}")

    print(f"Database: {database}")
    print(f"Database user: {user}")
    print(f"Postgres: {version}")
    print(f"pgvector: {vector_version}")
    print(f"Tables: {', '.join(REQUIRED_TABLES)}")
    print(f"Embedding column: {embedding_type}")
    print(f"Role-list column: {role_list_type}")
    print("HNSW index: present")
    print("RLS: enabled and forced")
    print("Supabase database check passed.")


if __name__ == "__main__":
    main()
