import io
import logging
from dataclasses import dataclass

from app.config import get_settings

logger = logging.getLogger(__name__)

_ocr = None
_ocr_failed = False


@dataclass(frozen=True, slots=True)
class OcrStatus:
    configured: bool
    loaded: bool
    failure_code: str | None


def _get_ocr():
    global _ocr, _ocr_failed
    if _ocr is None and not _ocr_failed:
        try:
            from rapidocr_onnxruntime import RapidOCR

            _ocr = RapidOCR()
            logger.info("RapidOCR loaded")
        except Exception:
            logger.exception("RapidOCR failed to load; OCR fallback is unavailable")
            _ocr_failed = True
    return _ocr


def warm_ocr() -> OcrStatus:
    settings = get_settings()
    if not settings.enable_ocr:
        return OcrStatus(configured=False, loaded=False, failure_code="disabled")
    model = _get_ocr()
    return OcrStatus(
        configured=True,
        loaded=model is not None,
        failure_code=None if model is not None else "model_load_failed",
    )


def ocr_image(data: bytes) -> str:
    """Run OCR over an image payload and return the extracted text."""
    model = _get_ocr()
    if model is None:
        return ""
    try:
        import numpy as np
        from PIL import Image

        image = Image.open(io.BytesIO(data)).convert("RGB")
        result, _elapsed = model(np.array(image))
    except Exception:
        logger.exception("OCR failed for an image payload")
        return ""
    if not result:
        return ""
    lines = [
        str(item[1]).strip()
        for item in result
        if len(item) > 1 and str(item[1]).strip()
    ]
    return "\n".join(lines)


def ocr_pdf_pages(data: bytes, *, max_pages: int) -> list[str]:
    """Render PDF pages to images and OCR each; return per-page text."""
    try:
        import pypdfium2 as pdfium
        from PIL import Image

        document = pdfium.PdfDocument(data)
    except Exception:
        logger.exception("OCR PDF rendering is unavailable")
        return []
    try:
        pages: list[str] = []
        for index in range(min(len(document), max_pages)):
            page = document[index]
            bitmap = page.render(scale=2)
            image: Image.Image = bitmap.to_pil()
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            pages.append(ocr_image(buffer.getvalue()))
        return pages
    finally:
        document.close()
