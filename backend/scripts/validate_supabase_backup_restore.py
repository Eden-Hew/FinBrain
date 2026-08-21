"""Reconstruct and byte-verify a Supabase backup in disposable PostgreSQL.

Validation tables intentionally use ``bytea`` columns. PostgreSQL binary COPY
streams contain field boundaries and each type's exact binary payload, so this
loads every backed-up field and permits a byte-for-byte re-export comparison
without requiring Supabase-only extensions such as pgvector.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
from pathlib import Path

import psycopg
from psycopg import sql


def _stream_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with gzip.open(path, "rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _copy_in(connection, qualified, source: Path) -> None:
    with connection.cursor().copy(
        sql.SQL("copy {} from stdin with (format binary)").format(qualified)
    ) as copy:
        with gzip.open(source, "rb") as handle:
            while block := handle.read(1024 * 1024):
                copy.write(block)


def _copy_out_hash(connection, qualified) -> str:
    digest = hashlib.sha256()
    with connection.cursor().copy(
        sql.SQL("copy (select * from {}) to stdout with (format binary)").format(qualified)
    ) as copy:
        for block in copy:
            digest.update(block)
    return digest.hexdigest()


def validate(database_url: str, backup: Path, storage_output: Path) -> None:
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    with psycopg.connect(database_url, autocommit=True) as connection:
        for schema_name in manifest["schemas"]:
            if schema_name == "public":
                continue
            connection.execute(
                sql.SQL("create schema if not exists {}").format(sql.Identifier(schema_name))
            )
        restored_rows = 0
        for table in manifest["tables"]:
            schema_name = table["schema_name"]
            table_name = table["table_name"]
            qualified = sql.SQL("{}.{}").format(
                sql.Identifier(schema_name), sql.Identifier(table_name)
            )
            definitions = sql.SQL(", ").join(
                sql.SQL("{} bytea").format(sql.Identifier(column)) for column in table["columns"]
            )
            connection.execute(sql.SQL("drop table if exists {} cascade").format(qualified))
            connection.execute(sql.SQL("create table {} ({})").format(qualified, definitions))
            source = backup / table["file"]
            _copy_in(connection, qualified, source)
            row_count = connection.execute(
                sql.SQL("select count(*) from {}").format(qualified)
            ).fetchone()[0]
            if row_count != table["row_count"]:
                raise RuntimeError(
                    f"row_count_mismatch:{schema_name}.{table_name}:"
                    f"{row_count}!={table['row_count']}"
                )
            if _copy_out_hash(connection, qualified) != _stream_hash(source):
                raise RuntimeError(f"binary_payload_mismatch:{schema_name}.{table_name}")
            restored_rows += row_count
            print(f"restored {schema_name}.{table_name}: {row_count} row(s), exact")

    storage_output.mkdir(parents=True, exist_ok=True)
    restored_objects = 0
    restored_bytes = 0
    root = storage_output.resolve()
    for item in manifest["storage_objects"]:
        target = (root / item["bucket_id"] / item["name"]).resolve()
        if root not in target.parents:
            raise RuntimeError(f"unsafe_storage_path:{item['name']}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(backup / item["file"], target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != item["sha256"] or target.stat().st_size != item["bytes"]:
            raise RuntimeError(f"storage_payload_mismatch:{item['bucket_id']}/{item['name']}")
        restored_objects += 1
        restored_bytes += target.stat().st_size
    if restored_rows != manifest["database_row_count"]:
        raise RuntimeError("database_total_mismatch")
    if restored_objects != manifest["storage_object_count"]:
        raise RuntimeError("storage_object_total_mismatch")
    if restored_bytes != manifest["storage_bytes"]:
        raise RuntimeError("storage_byte_total_mismatch")
    print(
        f"restore verified: {len(manifest['tables'])} tables, {restored_rows} rows, "
        f"{restored_objects} storage objects, {restored_bytes} storage bytes"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--storage-output", required=True, type=Path)
    args = parser.parse_args()
    validate(
        args.database_url,
        args.backup.resolve(),
        args.storage_output.resolve(),
    )


if __name__ == "__main__":
    main()
