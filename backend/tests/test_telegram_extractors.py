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
    )
    monkeypatch.setattr(extractors, "get_settings", lambda: settings)
    return settings


def test_text_and_email_extraction_are_bounded(extractor_settings):
    text = extractors.extract_document(
        b"A customer note.\r\nSecond line.", filename="note.txt", mime_type="text/plain"
    )
    assert text.text == "A customer note.\nSecond line."

    email = extractors.extract_document(
        b"Subject: Test\r\nFrom: person@example.com\r\nContent-Type: text/html\r\n\r\n"
        b"<style>bad</style><script>bad()</script><p>Hello</p>",
        filename="message.eml",
        mime_type="message/rfc822",
    )
    assert "Hello" in email.text
    assert "bad()" not in email.text


def test_unsupported_and_oversized_files_are_rejected(extractor_settings):
    with pytest.raises(extractors.ExtractionError, match="unsupported_file_type"):
        extractors.extract_document(b"x", filename="archive.zip", mime_type="application/zip")
    extractor_settings.telegram_max_file_bytes = 1
    with pytest.raises(extractors.ExtractionError, match="file_too_large"):
        extractors.extract_document(b"xx", filename="note.txt", mime_type="text/plain")
    extractor_settings.telegram_max_file_bytes = 10_000
    with pytest.raises(extractors.ExtractionError, match="unsupported_file_type"):
        extractors.extract_document(
            b"hello", filename="note.txt", mime_type="application/x-msdownload"
        )


def test_pdf_signature_and_docx_signature_are_checked(extractor_settings):
    with pytest.raises(extractors.ExtractionError, match="invalid_file_signature"):
        extractors.extract_document(b"not pdf", filename="note.pdf", mime_type="application/pdf")
    with pytest.raises(extractors.ExtractionError, match="invalid_file_signature"):
        extractors.extract_document(
            b"not docx",
            filename="note.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
