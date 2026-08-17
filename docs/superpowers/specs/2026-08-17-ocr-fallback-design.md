# OCR Fallback Layer in the Ingestion Pipeline

Date: 2026-08-17

## Problem

The ingestion pipeline only extracts text from `.txt .md .csv .eml .pdf .docx`. Image files fail
with `unsupported_file_type` before any parsing, and scanned (non-text) PDFs fail with
`no_extractable_text` because pypdf returns an empty string. Users cannot ingest invoices,
receipts, or photos that are image-based.

## Goal

Insert an OCR layer inside `extract_document` so that images and non-text PDFs yield text that
feeds the existing canonical ingestion pipeline, exactly like today's text-based uploads. OCR runs
locally (privacy-first), is enabled by default, and records provenance in record metadata.

## Scope

- `backend/app/integrations/telegram/extractors.py`
- `backend/app/integrations/ocr/` (new package: `engine.py`)
- `backend/app/config.py`
- `backend/app/main.py` (health flag)
- `backend/app/integrations/telegram/types.py` (ExtractedContent)
- `backend/app/services/upload_ingestion.py` (metadata provenance)
- `backend/app/integrations/telegram/adapter.py` (metadata provenance)
- `backend/pyproject.toml` (dependencies)
- `backend/scripts/prewarm_detector.py`
- Frontend `accept` attributes (`Ingestion.tsx`, `Agents.tsx`)
- `README.md`

Out of scope: PyMuPDF/pdfminer text-layer fallbacks, LLM vision OCR (privacy violation), Tesseract
(system binary dependency).

## Architecture

`extract_document` is the single chokepoint already used by web upload, email attachments, and
Telegram documents. Routes, services, and the canonical pipeline are untouched.

```
extract_document(data, filename, mime_type)
 ├─ .txt/.md/.csv/.eml/.docx → existing parsers (unchanged)
 ├─ .png/.jpg/.jpeg/.webp/.bmp/.tiff → NEW: decode image → RapidOCR → ExtractedContent
 └─ .pdf → pypdf extract_text()
            └─ if extracted text < ocr_min_text_chars:
                pypdfium2 render each page → RapidOCR per page → reassemble
```

## OCR Engine (`backend/app/integrations/ocr/engine.py`)

Mirrors the GLiNER lazy-load pattern in `app/security/detect.py`:

- `ocr_image(data: bytes) -> str` — decode image (Pillow), run RapidOCR, return joined text.
- `warm_ocr() -> OcrStatus` — lazily load RapidOCR models; failure is non-fatal (falls back to
  the previous `no_extractable_text` behavior).
- Module-level `_ocr`/`_ocr_failed` state; `enable_ocr` config gates everything.
- Local-only. No LLM vision, no system binaries.

## Config (`config.py`)

```python
enable_ocr: bool = True
ocr_min_text_chars: int = 40
ocr_max_pages: int = 20
ocr_max_image_bytes: int = 10_000_000
```

All added to the `Settings` whitelist. `/health` gains `"ocr_enabled": settings.enable_ocr`.

## Extraction Changes (`extractors.py`)

- Extend `ALLOWED_EXTENSIONS` with `.png .jpg .jpeg .webp .bmp .tiff` and add matching
  `MIME_TYPES` entries (real MIME + `application/octet-stream`).
- `_extract_image(data, suffix)` → `ocr_image(data)` → `ExtractedContent(input_kind=suffix)`.
- `_extract_pdf`: keep pypdf path; when total text length < `ocr_min_text_chars` and OCR enabled,
  render pages with pypdfium2 and OCR them. `page_count` preserved.
- `ExtractedContent` gains optional `extraction_method: str | None` (`"text"` | `"ocr"`).
- `extract_document` sets `extraction_method="ocr"` when OCR produced the text, else `"text"`.

## Metadata Provenance

- `upload_ingestion._document_record`: add `extraction_method` to record metadata when set.
- `adapter.canonical_record` (Telegram): same, plus `page_count`.

## Dependencies (`pyproject.toml`)

- `rapidocr-onnxruntime>=1.3,<2`
- `pypdfium2>=4.30,<5`
- `Pillow>=10,<12`

All pip-only; no system binaries; preserves the uv-managed environment.

## Privacy and Safety

- OCR output is raw text entering `CanonicalIngestionRecord.text`, immediately tokenized by
  `protect_canonical_record`. The "raw never persisted" invariant holds.
- Bounds: `ocr_max_pages`, `ocr_max_image_bytes`, existing `telegram_max_file_bytes`,
  `_normalize` char cap, and the 10 MB web-upload body limit.

## Testing

- Mock `ocr_image`/pypdfium2; no model downloads in CI.
- New `tests/test_ocr_fallback.py`:
  - image path returns OCR text
  - scanned PDF (pypdf empty) triggers OCR
  - text-layer PDF does NOT trigger OCR
  - `extraction_method` metadata flows through
  - unsupported type still raises
- Existing extractor tests unchanged and passing.

## Verification

- `uv run --extra dev pytest -q`
- `uv run --extra dev ruff check app tests scripts`
- `scripts/prepare_demo.ps1 -SkipNetworkChecks`
- Manual: upload scanned PDF + PNG via Ingestion tab → protected preview shows OCR text → commit
  reports `ready`.
