from pathlib import Path

from .base import OcrPage


class MockOCR:
    name = "ocr_mock"

    def __init__(self):
        self.calls: list[int] = []  # lets tests assert "only scanned pages were OCR'd"

    def ocr_pdf_page(self, pdf_path: Path, page_index: int) -> OcrPage:
        self.calls.append(page_index)
        return OcrPage(text=f"[mock OCR text for page {page_index + 1}]", confidence=0.9)
