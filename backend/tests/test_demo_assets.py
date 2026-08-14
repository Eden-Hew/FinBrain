from pathlib import Path

from app.integrations.structured_csv.adapter import adapt_invoice_row, batch_reference
from app.integrations.structured_csv.parser import parse_invoice_csv

DEMO_DIR = Path(__file__).parents[2] / "demo"


def test_invoice_demo_fixture_is_valid_and_independently_addressable():
    data = (DEMO_DIR / "invoice_register.csv").read_bytes()
    parsed = parse_invoice_csv(data)
    batch_ref = batch_reference(data)
    records = [adapt_invoice_row(row, batch_ref=batch_ref) for row in parsed.rows]

    assert parsed.total_rows == 4
    assert len(parsed.rows) == 4
    assert parsed.issues == []
    assert len({record.source_record_id for record in records}) == 4
    assert all(record.source_system == "spreadsheet" for record in records)


def test_demo_assets_are_marked_synthetic_and_contain_no_configuration_secrets():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in DEMO_DIR.iterdir())
    assert "SYNTHETIC DEMONSTRATION RECORD" in combined
    assert "your-morpheus-key" not in combined
    assert "postgresql://" not in combined
    assert "TOKEN_ROOT_SECRET=" not in combined
    assert "GEMINI_API_KEY=" not in combined
