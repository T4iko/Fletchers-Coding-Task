from __future__ import annotations

from typing import Iterator, Optional, Union

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from .base import Chunk, DocumentInfo, ExtractionError, ExtractionResult, ProgressFn
from .sniff import DOCX


def _iter_blocks(d) -> Iterator[Union[Paragraph, Table]]:
    """Body order matters: python-docx exposes paragraphs and tables separately,
    so walk the XML to keep them interleaved as authored."""
    for child in d.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, d)
        elif child.tag.endswith("}tbl"):
            yield Table(child, d)


def _table_to_markdown(t: Table) -> str:
    rows = [[c.text.strip().replace("\n", " ") for c in r.cells] for r in t.rows]
    if not rows:
        return ""
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * len(rows[0])]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


class DocxExtractor:
    name = "docx"

    def can_handle(self, doc: DocumentInfo) -> float:
        return 1.0 if doc.mime == DOCX else 0.0

    def extract(self, doc: DocumentInfo, on_progress: Optional[ProgressFn] = None) -> ExtractionResult:
        try:
            d = Document(str(doc.path))
        except Exception as e:
            raise ExtractionError(f"Corrupt or unreadable DOCX: {e}") from e

        blocks = list(_iter_blocks(d))
        chunks: list[Chunk] = []
        for n, b in enumerate(blocks, 1):
            if isinstance(b, Paragraph):
                text = b.text.strip()
                if text:
                    is_heading = (b.style.name or "").lower().startswith(("heading", "title"))
                    chunks.append(Chunk(text=text, type="heading" if is_heading else "paragraph",
                                        method="docx", metadata={"style": b.style.name}))
            else:
                md = _table_to_markdown(b)
                if md:
                    chunks.append(Chunk(text=md, type="table", method="docx"))
            if on_progress and (n % 50 == 0 or n == len(blocks)):
                on_progress(n, len(blocks))  # DOCX has no pages; progress is per block

        props = d.core_properties
        return ExtractionResult(chunks=chunks, method="docx",
                                metadata={"title": props.title, "author": props.author})
