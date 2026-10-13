"""PDF extractor with PER-PAGE routing: digital pages use the text layer, pages with
(almost) no text are sent to OCR. Mixed documents are therefore handled naturally and
OCR cost is limited to the pages that need it."""
from __future__ import annotations

from typing import Optional

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.ocr.base import OCRProvider

from .base import Chunk, DocumentInfo, EncryptedDocument, ExtractionError, ExtractionResult, ProgressFn
from .sniff import PDF

MIN_CHARS_PER_PAGE = 25  # below this we treat the page as scanned/image-only


def classify_page(text: str, min_chars: int = MIN_CHARS_PER_PAGE) -> str:
    """'digital' | 'scanned'. Heuristic; extend with image-coverage / garbage-text checks
    (e.g. scanned PDFs that already carry a junk OCR layer)."""
    return "digital" if len(text.strip()) >= min_chars else "scanned"


class PdfExtractor:
    name = "pdf"

    def __init__(self, ocr: OCRProvider, min_chars: int = MIN_CHARS_PER_PAGE):
        self.ocr = ocr
        self.min_chars = min_chars

    def can_handle(self, doc: DocumentInfo) -> float:
        return 1.0 if doc.mime == PDF else 0.0

    def extract(self, doc: DocumentInfo, on_progress: Optional[ProgressFn] = None) -> ExtractionResult:
        try:
            reader = PdfReader(doc.path)
            if reader.is_encrypted and not reader.decrypt(""):  # many PDFs use an empty user password
                raise EncryptedDocument("PDF is password-protected")
            total = len(reader.pages)
        except PdfReadError as e:
            raise ExtractionError(f"Corrupt or unreadable PDF: {e}") from e

        chunks: list[Chunk] = []
        warnings: list[str] = []
        methods: set[str] = set()

        for i, page in enumerate(reader.pages):
            try:
                text = (page.extract_text() or "").strip()
            except Exception as e:  # one bad page shouldn't sink the document
                warnings.append(f"page {i + 1}: text extraction failed ({e}); trying OCR")
                text = ""

            if classify_page(text, self.min_chars) == "digital":
                chunks.append(Chunk(text=text, type="page", page=i + 1, method="pdf_text"))
                methods.add("pdf_text")
            else:
                ocr = self.ocr.ocr_pdf_page(doc.path, i)
                chunks.append(Chunk(text=ocr.text, type="page", page=i + 1,
                                    method="pdf_ocr", confidence=ocr.confidence,
                                    metadata={"ocr_provider": self.ocr.name}))
                methods.add("pdf_ocr")
                warnings.append(f"page {i + 1} routed to OCR ({self.ocr.name})")
                if ocr.confidence < 0.6:
                    warnings.append(f"page {i + 1}: low OCR confidence ({ocr.confidence:.2f})")

            if on_progress:
                on_progress(i + 1, total)

        method = "pdf_mixed" if len(methods) > 1 else (methods.pop() if methods else "pdf_text")
        return ExtractionResult(chunks=chunks, method=method, warnings=warnings,
                                metadata={"pages": total})
