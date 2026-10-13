"""The contract every format plugin implements. Nothing else in the codebase should
need to change when a new format is added."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal, Optional, Protocol

ChunkType = Literal["paragraph", "heading", "table", "page"]
ProgressFn = Callable[[int, int], None]  # (units_done, units_total)


class ExtractionError(Exception):
    """Expected, user-explainable failure (message is shown in the UI)."""


class UnsupportedFormat(ExtractionError):
    pass


class EncryptedDocument(ExtractionError):
    pass


@dataclass(frozen=True)
class DocumentInfo:
    path: Path
    filename: str
    mime: str  # sniffed from content
    size: int
    sha256: str


@dataclass
class Chunk:
    text: str
    type: ChunkType = "paragraph"
    page: Optional[int] = None  # 1-based, None if format has no pages
    method: str = ""  # provenance: 'pdf_text', 'pdf_ocr', 'docx'
    confidence: Optional[float] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ExtractionResult:
    chunks: list[Chunk]
    method: str  # overall: 'pdf_text' | 'pdf_ocr' | 'pdf_mixed' | 'docx'
    metadata: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class Extractor(Protocol):
    name: str

    def can_handle(self, doc: DocumentInfo) -> float:
        """0.0 = no, 1.0 = definitely. Router picks the highest score."""
        ...

    def extract(self, doc: DocumentInfo, on_progress: Optional[ProgressFn] = None) -> ExtractionResult: ...
