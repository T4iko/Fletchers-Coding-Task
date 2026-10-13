from __future__ import annotations

from .base import DocumentInfo, Extractor, UnsupportedFormat

_EXTRACTORS: list[Extractor] = []
MIN_CONFIDENCE = 0.1


def register(extractor: Extractor) -> Extractor:
    if any(e.name == extractor.name for e in _EXTRACTORS):
        raise ValueError(f"duplicate extractor name: {extractor.name}")
    _EXTRACTORS.append(extractor)
    return extractor


def clear() -> None:
    _EXTRACTORS.clear()


def route(doc: DocumentInfo) -> Extractor:
    scored = sorted(((e.can_handle(doc), e) for e in _EXTRACTORS), key=lambda t: -t[0])
    if not scored or scored[0][0] < MIN_CONFIDENCE:
        hint = ""
        if doc.mime == "application/x-ole-storage":
            hint = " (legacy Office format or password-protected file)"
        raise UnsupportedFormat(f"No extractor for {doc.filename!r} [{doc.mime}]{hint}")
    return scored[0][1]
