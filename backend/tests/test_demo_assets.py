from pathlib import Path

from app.integrations.structured_csv.adapter import adapt_invoice_row, batch_reference
from app.integrations.structured_csv.parser import parse_invoice_csv
from app.integrations.telegram.extractors import extract_document

DEMO_DIR = Path(__file__).parents[2] / "demo"


def test_invoice_demo_fixtures_are_valid_and_independently_addressable():
    for filename in ("invoice_register.csv", "chat_upload_invoice_register.csv"):
        data = (DEMO_DIR / filename).read_bytes()
        parsed = parse_invoice_csv(data)
        batch_ref = batch_reference(data)
        records = [adapt_invoice_row(row, batch_ref=batch_ref) for row in parsed.rows]

        assert parsed.total_rows == 4
        assert len(parsed.rows) == 4
        assert parsed.issues == []
        assert len({record.source_record_id for record in records}) == 4
        assert all(record.source_system == "spreadsheet" for record in records)


def test_invalid_invoice_demo_fixture_exercises_safe_validation():
    data = (DEMO_DIR / "invoice_register_invalid.csv").read_bytes()
    parsed = parse_invoice_csv(data)

    assert parsed.total_rows == 3
    assert len(parsed.rows) == 1
    assert {issue.code for issue in parsed.issues} == {
        "duplicate_invoice_id",
        "invalid_amount",
        "invalid_due_date",
    }


def test_email_demo_fixture_can_be_extracted_for_upload():
    data = (DEMO_DIR / "sample_approval_email.eml").read_bytes()
    extracted = extract_document(
        data,
        filename="sample_approval_email.eml",
        mime_type="message/rfc822",
    )

    assert extracted.input_kind == "eml"
    assert "DEMO-INV-1001" in extracted.text
    assert "RM 4,500" in extracted.text


def test_demo_assets_are_marked_synthetic_and_contain_no_configuration_secrets():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in DEMO_DIR.iterdir())
    assert "SYNTHETIC DEMONSTRATION RECORD" in combined
    assert "your-morpheus-key" not in combined
    assert "postgresql://" not in combined
    assert "TOKEN_ROOT_SECRET=" not in combined
    assert "GEMINI_API_KEY=" not in combined
