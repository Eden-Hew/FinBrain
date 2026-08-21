"""Create a complete, read-only local backup of the configured Supabase project.

The backup contains binary PostgreSQL COPY streams for every table in the
selected schemas, an exact catalog manifest, the repository migrations, every
Storage object byte-for-byte, row/object counts, and SHA-256 checksums.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import psycopg
from psycopg import sql

from app.config import get_settings

DEFAULT_SCHEMAS = (
    "auth",
    "public",
    "realtime",
    "storage",
    "supabase_migrations",
    "vault",
)


def _database_url() -> str:
    value = get_settings().database_url
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def _rows(cursor) -> list[dict[str, Any]]:
    names = [column.name for column in cursor.description or ()]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def _json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _catalog(connection, schemas: tuple[str, ...]) -> dict[str, Any]:
    params = {"schemas": list(schemas)}
    queries = {
        "extensions": """
            select e.extname, e.extversion, n.nspname as schema_name
            from pg_extension e join pg_namespace n on n.oid=e.extnamespace
            order by e.extname
        """,
        "columns": """
            select table_schema, table_name, ordinal_position, column_name,
                   data_type, udt_schema, udt_name, is_nullable, column_default,
                   is_identity, identity_generation, is_generated, generation_expression
            from information_schema.columns
            where table_schema = any(%(schemas)s)
            order by table_schema, table_name, ordinal_position
        """,
        "constraints": """
            select n.nspname as schema_name, c.relname as table_name,
                   con.conname, con.contype,
                   pg_get_constraintdef(con.oid, true) as definition
            from pg_constraint con
            join pg_class c on c.oid=con.conrelid
            join pg_namespace n on n.oid=c.relnamespace
            where n.nspname = any(%(schemas)s)
            order by n.nspname, c.relname, con.conname
        """,
        "indexes": """
            select schemaname as schema_name, tablename as table_name,
                   indexname, indexdef
            from pg_indexes where schemaname = any(%(schemas)s)
            order by schemaname, tablename, indexname
        """,
        "policies": """
            select schemaname as schema_name, tablename as table_name,
                   policyname, permissive, roles, cmd, qual, with_check
            from pg_policies where schemaname = any(%(schemas)s)
            order by schemaname, tablename, policyname
        """,
        "triggers": """
            select n.nspname as schema_name, c.relname as table_name,
                   t.tgname, pg_get_triggerdef(t.oid, true) as definition
            from pg_trigger t
            join pg_class c on c.oid=t.tgrelid
            join pg_namespace n on n.oid=c.relnamespace
            where not t.tgisinternal and n.nspname = any(%(schemas)s)
            order by n.nspname, c.relname, t.tgname
        """,
        "views": """
            select schemaname as schema_name, viewname, definition
            from pg_views where schemaname = any(%(schemas)s)
            order by schemaname, viewname
        """,
        "functions": """
            select n.nspname as schema_name, p.proname,
                   pg_get_function_identity_arguments(p.oid) as identity_arguments,
                   pg_get_functiondef(p.oid) as definition
            from pg_proc p join pg_namespace n on n.oid=p.pronamespace
            where n.nspname = any(%(schemas)s)
            order by n.nspname, p.proname, identity_arguments
        """,
        "sequences": """
            select schemaname as schema_name, sequencename, data_type,
                   start_value, min_value, max_value, increment_by,
                   cycle, cache_size, last_value
            from pg_sequences where schemaname = any(%(schemas)s)
            order by schemaname, sequencename
        """,
        "enums": """
            select n.nspname as schema_name, t.typname,
                   e.enumsortorder, e.enumlabel
            from pg_type t
            join pg_enum e on e.enumtypid=t.oid
            join pg_namespace n on n.oid=t.typnamespace
            where n.nspname = any(%(schemas)s)
            order by n.nspname, t.typname, e.enumsortorder
        """,
        "roles": """
            select rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb,
                   rolcanlogin, rolreplication, rolbypassrls, rolconnlimit,
                   rolvaliduntil
            from pg_roles order by rolname
        """,
    }
    result: dict[str, Any] = {}
    for name, statement in queries.items():
        with connection.cursor() as cursor:
            cursor.execute(statement, params if "%(schemas)s" in statement else None)
            result[name] = _rows(cursor)
    return result


def _table_inventory(connection, schemas: tuple[str, ...]) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select n.nspname as schema_name, c.relname as table_name,
                   c.relkind, c.relrowsecurity, c.relforcerowsecurity
            from pg_class c join pg_namespace n on n.oid=c.relnamespace
            where n.nspname = any(%s) and c.relkind in ('r','p')
            order by n.nspname, c.relname
            """,
            (list(schemas),),
        )
        return _rows(cursor)


def _dump_tables(connection, output: Path, tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    data_dir = output / "database" / "tables"
    data_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    for table in tables:
        schema_name = str(table["schema_name"])
        table_name = str(table["table_name"])
        qualified = sql.SQL("{}.{}").format(sql.Identifier(schema_name), sql.Identifier(table_name))
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("select count(*) from {}").format(qualified))
            row_count = int(cursor.fetchone()[0])
            cursor.execute(sql.SQL("select * from {} limit 0").format(qualified))
            columns = [column.name for column in cursor.description or ()]
        filename = f"{schema_name}__{table_name}.copy.gz"
        target = data_dir / filename
        with (
            target.open("wb") as raw_handle,
            gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0) as compressed,
        ):
            with connection.cursor().copy(
                sql.SQL("copy (select * from {}) to stdout with (format binary)").format(qualified)
            ) as copy:
                for block in copy:
                    compressed.write(block)
        item = {
            **table,
            "columns": columns,
            "row_count": row_count,
            "file": f"database/tables/{filename}",
            "sha256": _sha256(target),
            "compressed_bytes": target.stat().st_size,
        }
        manifest.append(item)
        print(f"database {schema_name}.{table_name}: {row_count} row(s)")
    return manifest


def _storage_rows(connection) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            select bucket_id, name, metadata
            from storage.objects
            where name is not null and metadata is not null
            order by bucket_id, name
            """
        )
        return _rows(cursor)


def _download_storage(output: Path, objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    settings = get_settings()
    if objects and (not settings.supabase_url or not settings.supabase_service_role_key):
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    target_dir = output / "storage" / "objects"
    target_dir.mkdir(parents=True, exist_ok=True)
    headers = {
        "apikey": settings.supabase_service_role_key or "",
        "authorization": f"Bearer {settings.supabase_service_role_key or ''}",
    }
    manifest: list[dict[str, Any]] = []
    with httpx.Client(headers=headers, timeout=60.0, follow_redirects=True) as client:
        for index, item in enumerate(objects, 1):
            bucket = str(item["bucket_id"])
            name = str(item["name"])
            object_id = hashlib.sha256(f"{bucket}\0{name}".encode()).hexdigest()
            target = target_dir / f"{object_id}.bin"
            url = (
                f"{settings.supabase_url.rstrip('/')}/storage/v1/object/authenticated/"
                f"{quote(bucket, safe='')}/{quote(name, safe='/')}"
            )
            with client.stream("GET", url) as response:
                response.raise_for_status()
                with target.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        handle.write(chunk)
            manifest.append(
                {
                    "bucket_id": bucket,
                    "name": name,
                    "metadata": item["metadata"],
                    "file": f"storage/objects/{target.name}",
                    "bytes": target.stat().st_size,
                    "sha256": _sha256(target),
                }
            )
            print(f"storage {index}/{len(objects)}: {bucket}/{name}")
    return manifest


def _write_checksums(output: Path) -> None:
    checksum_path = output / "SHA256SUMS.txt"
    files = sorted(path for path in output.rglob("*") if path.is_file() and path != checksum_path)
    checksum_path.write_text(
        "".join(f"{_sha256(path)}  {path.relative_to(output).as_posix()}\n" for path in files),
        encoding="utf-8",
    )


def backup(output: Path, schemas: tuple[str, ...]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    existing = [path for path in output.iterdir() if path.stat().st_size > 0]
    if existing:
        raise RuntimeError(f"backup_directory_not_empty:{output}")
    zero_files = [path for path in output.iterdir() if path.is_file()]
    for path in zero_files:
        path.unlink()

    with psycopg.connect(_database_url(), prepare_threshold=None) as connection:
        connection.execute("begin isolation level repeatable read read only")
        with connection.cursor() as cursor:
            cursor.execute(
                "select current_database(), current_user, current_setting('server_version')"
            )
            database_name, database_user, server_version = cursor.fetchone()
        tables = _table_inventory(connection, schemas)
        catalog = _catalog(connection, schemas)
        storage_rows = _storage_rows(connection) if "storage" in schemas else []
        table_manifest = _dump_tables(connection, output, tables)
        connection.rollback()

    storage_manifest = _download_storage(output, storage_rows)
    migrations_source = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
    shutil.copytree(migrations_source, output / "database" / "migrations")
    _json(output / "database" / "catalog.json", catalog)
    manifest = {
        "format_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "database_name": database_name,
        "database_user": database_user,
        "server_version": server_version,
        "schemas": list(schemas),
        "tables": table_manifest,
        "database_row_count": sum(item["row_count"] for item in table_manifest),
        "storage_objects": storage_manifest,
        "storage_object_count": len(storage_manifest),
        "storage_bytes": sum(item["bytes"] for item in storage_manifest),
    }
    _json(output / "manifest.json", manifest)
    (output / "README.txt").write_text(
        "FinBrain pre-reset Supabase backup. Contains sensitive encrypted business, "
        "Auth, audit, and Storage data. Do not commit or share. Table files are "
        "gzip-compressed PostgreSQL binary COPY streams and require the matching "
        "schema/server compatibility recorded in manifest.json.\n",
        encoding="utf-8",
    )
    _write_checksums(output)
    print(
        f"backup complete: {len(table_manifest)} tables, "
        f"{manifest['database_row_count']} rows, {len(storage_manifest)} storage objects"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up all configured Supabase data locally.")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--schema", action="append", dest="schemas")
    args = parser.parse_args()
    schemas = tuple(dict.fromkeys(args.schemas or DEFAULT_SCHEMAS))
    backup(args.output.resolve(), schemas)


if __name__ == "__main__":
    main()
