from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class OcrPage:
    text: str
    confidence: float  # 0..1


class OCRProvider(Protocol):
    name: str

    def ocr_pdf_page(self, pdf_path: Path, page_index: int) -> OcrPage:
        """Real impl: render page -> image (pypdfium2) -> Textract / Vision / Tesseract."""
        ...
