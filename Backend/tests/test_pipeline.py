import hashlib
import uuid
from pathlib import Path

import pytest


from app.core.db import connect, init_db
from app.core.pipeline import process_document
from app.extractors import register_defaults
from app.extractors.base import DocumentInfo, UnsupportedFormat
from app.extractors.sniff import DOCX, PDF, sniff_mime
from app.extractors import registry
from app.ocr.mock import MockOCR
from helpers import make_docx, make_pdf

LONG = "This is a digital page with plenty of real extractable text on it."


def info(path: Path) -> DocumentInfo:
    return DocumentInfo(path, path.name, sniff_mime(path), path.stat().st_size,
                        hashlib.sha256(path.read_bytes()).hexdigest())


@pytest.fixture
def ocr():
    o = MockOCR()
    register_defaults(o)
    return o

def test_sniff_ignores_extension(tmp_path):
    p = make_pdf(tmp_path / "actually.docx", [LONG])
    assert sniff_mime(p) == PDF
    assert sniff_mime(make_docx(tmp_path / "x.bin")) == DOCX


def test_digital_pdf_never_calls_ocr(tmp_path, ocr):
    d = info(make_pdf(tmp_path / "a.pdf", [LONG, LONG]))
    res = registry.route(d).extract(d)
    assert res.method == "pdf_text" and ocr.calls == []


def test_scanned_pdf_goes_to_ocr(tmp_path, ocr):
    d = info(make_pdf(tmp_path / "s.pdf", [None, None]))
    res = registry.route(d).extract(d)
    assert res.method == "pdf_ocr" and ocr.calls == [0, 1]


def test_mixed_pdf_only_ocrs_scanned_pages(tmp_path, ocr):
    d = info(make_pdf(tmp_path / "m.pdf", [LONG, None, LONG]))
    res = registry.route(d).extract(d)
    assert res.method == "pdf_mixed"
    assert ocr.calls == [1]
    assert [c.method for c in res.chunks] == ["pdf_text", "pdf_ocr", "pdf_text"]
    assert any("page 2 routed to OCR" in w for w in res.warnings)


def test_docx_preserves_structure(tmp_path, ocr):
    d = info(make_docx(tmp_path / "d.docx"))
    res = registry.route(d).extract(d)
    assert [c.type for c in res.chunks] == ["heading", "paragraph", "table"]


def test_unsupported_format_raises(tmp_path, ocr):
    p = tmp_path / "x.txt"
    p.write_text("hello")
    with pytest.raises(UnsupportedFormat):
        registry.route(info(p))


def test_end_to_end_and_fts(tmp_path, ocr):
    db = str(tmp_path / "t.db")
    init_db(db)
    pdf = make_pdf(tmp_path / "e.pdf", [LONG, None])
    doc_id = str(uuid.uuid4())
    con = connect(db)
    with con:
        con.execute("INSERT INTO documents (id, filename, size, sha256, storage_path) VALUES (?,?,?,?,?)",
                    (doc_id, "e.pdf", pdf.stat().st_size, "x", str(pdf)))
    process_document(db, doc_id)
    row = con.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    assert row["status"] == "done" and row["method"] == "pdf_mixed"
    assert row["pages_done"] == row["pages_total"] == 2
    hits = con.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'extractable'").fetchall()
    assert len(hits) == 1
    process_document(db, doc_id)  # idempotent re-run
    assert con.execute("SELECT COUNT(*) FROM chunks WHERE document_id=?", (doc_id,)).fetchone()[0] == 2


def test_corrupt_pdf_fails_gracefully(tmp_path, ocr):
    db = str(tmp_path / "t.db")
    init_db(db)
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 this is not really a pdf")
    con = connect(db)
    with con:
        con.execute("INSERT INTO documents (id, filename, size, sha256, storage_path) VALUES ('1','bad.pdf',1,'x',?)",
                    (str(bad),))
    process_document(db, "1")
    row = con.execute("SELECT status, error FROM documents WHERE id='1'").fetchone()
    assert row["status"] == "failed" and row["error"]
