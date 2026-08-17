from types import SimpleNamespace

import pytest

from app.integrations.telegram import extractors


@pytest.fixture
def extractor_settings(monkeypatch):
    settings = SimpleNamespace(
        telegram_max_file_bytes=10_000,
        telegram_max_extracted_chars=5_000,
        telegram_max_pdf_pages=5,
        telegram_max_docx_members=100,
        telegram_max_docx_uncompressed_bytes=100_000,
        enable_ocr=True,
        ocr_min_text_chars=40,
        ocr_max_pages=5,
        ocr_max_image_bytes=10_000,
    )
    monkeypatch.setattr(extractors, "get_settings", lambda: settings)
    return settings


class FakePage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


class FakeReader:
    is_encrypted = False

    def __init__(self, pages: list[FakePage]) -> None:
        self.pages = pages


def test_image_upload_is_extracted_via_ocr(extractor_settings, monkeypatch):
    monkeypatch.setattr(extractors, "ocr_image", lambda data: "Invoice #0042 from supplier")
    result = extractors.extract_document(
        b"fake-png-bytes", filename="invoice.png", mime_type="image/png"
    )
    assert result.text == "Invoice #0042 from supplier"
    assert result.input_kind == "png"
    assert result.extraction_method == "ocr"


def test_scanned_pdf_falls_back_to_ocr(extractor_settings, monkeypatch):
    monkeypatch.setattr(
        extractors,
        "PdfReader",
        lambda _stream: FakeReader([FakePage(""), FakePage("")]),
    )
    monkeypatch.setattr(
        extractors,
        "ocr_pdf_pages",
        lambda data, max_pages: ["Page A text", "Page B text"],
    )
    result = extractors.extract_document(
        b"%PDF-1.4 fake scanned", filename="scan.pdf", mime_type="application/pdf"
    )
    assert "Page A text" in result.text
    assert "Page B text" in result.text
    assert result.page_count == 2
    assert result.extraction_method == "ocr"


def test_text_layer_pdf_does_not_trigger_ocr(extractor_settings, monkeypatch):
    monkeypatch.setattr(extractors, "PdfReader", lambda _stream: FakeReader([FakePage("A" * 200)]))
    monkeypatch.setattr(
        extractors,
        "ocr_pdf_pages",
        lambda data, max_pages: pytest.fail("OCR must not run for a text-layer PDF"),
    )
    result = extractors.extract_document(
        b"%PDF-1.4 real text", filename="report.pdf", mime_type="application/pdf"
    )
    assert "A" * 200 in result.text
    assert result.extraction_method == "text"


def test_ocr_disabled_keeps_no_extractable_text(extractor_settings, monkeypatch):
    extractor_settings.enable_ocr = False
    monkeypatch.setattr(extractors, "PdfReader", lambda _stream: FakeReader([FakePage("")]))
    monkeypatch.setattr(
        extractors,
        "ocr_pdf_pages",
        lambda data, max_pages: pytest.fail("OCR disabled"),
    )
    with pytest.raises(extractors.ExtractionError, match="no_extractable_text"):
        extractors.extract_document(
            b"%PDF-1.4 scanned", filename="scan.pdf", mime_type="application/pdf"
        )


def test_unsupported_extension_still_rejected(extractor_settings, monkeypatch):
    monkeypatch.setattr(extractors, "ocr_image", lambda data: pytest.fail("OCR must not run"))
    with pytest.raises(extractors.ExtractionError, match="unsupported_file_type"):
        extractors.extract_document(b"x", filename="photo.svg", mime_type="image/svg+xml")


def test_upload_document_record_tags_ocr_method(monkeypatch):
    monkeypatch.setattr(extractors, "ocr_image", lambda data: "OCR text from image")
    from app.services.upload_ingestion import _document_record

    record, input_kind = _document_record(
        b"img",
        filename="invoice.png",
        mime_type="image/png",
        record_type="uploaded_document",
    )
    assert input_kind == "png"
    assert record.metadata["extraction_method"] == "ocr"


def test_telegram_adapter_tags_ocr_method():
    from datetime import UTC, datetime

    from app.integrations.telegram.adapter import canonical_record
    from app.integrations.telegram.types import ExtractedContent

    extracted = ExtractedContent(
        text="Scanned text",
        input_kind="pdf",
        mime_type="application/pdf",
        filename="scan.pdf",
        page_count=1,
        extraction_method="ocr",
    )
    record = canonical_record(
        chat_id=1,
        message_id=2,
        record_type="document",
        occurred_at=datetime.now(UTC),
        extracted=extracted,
        stable_content_ref="ref",
    )
    assert record.metadata["extraction_method"] == "ocr"
    assert record.metadata["page_count"] == "1"


def test_warm_ocr_reports_disabled(monkeypatch):
    from app.integrations.ocr import engine

    class DisabledSettings:
        enable_ocr = False

    monkeypatch.setattr(engine, "get_settings", lambda: DisabledSettings())
    status = engine.warm_ocr()
    assert status.configured is False
    assert status.failure_code == "disabled"


def test_ocr_image_returns_empty_when_model_unavailable(monkeypatch):
    from app.integrations.ocr import engine

    monkeypatch.setattr(engine, "_ocr", None)
    monkeypatch.setattr(engine, "_ocr_failed", True)

    class EnabledSettings:
        enable_ocr = True

    monkeypatch.setattr(engine, "get_settings", lambda: EnabledSettings())
    assert engine.ocr_image(b"not-a-real-image") == ""
