"""Wiring point: the ONLY file that changes when you add a format (plus the new module)."""
from app.ocr.base import OCRProvider
from app.ocr.mock import MockOCR

from . import registry
from .docx import DocxExtractor
from .pdf import PdfExtractor


def register_defaults(ocr: OCRProvider | None = None) -> None:
    registry.clear()
    registry.register(PdfExtractor(ocr or MockOCR()))
    registry.register(DocxExtractor())
    # registry.register(XlsxExtractor())   # <- adding a format
