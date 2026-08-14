"""Strict, privacy-preserving adapters for allowlisted structured CSV files."""

from app.integrations.structured_csv.service import ingest_structured_csv

__all__ = ["ingest_structured_csv"]
