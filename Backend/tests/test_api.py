import json

import pytest

from app import main
from app.core.db import connect
from helpers import LONG, make_docx, make_pdf


# ---------- upload -> process -> read (the happy path) ----------

def test_mixed_pdf_end_to_end(api, tmp_path):
    pdf = make_pdf(tmp_path / "m.pdf", [LONG, None, LONG])
    r = api.upload(pdf)
    assert r.status_code == 202
    assert r.json()["status"] == "queued"  # honest: processing happens after the response

    doc = api.client.get(f"/documents/{r.json()['id']}").json()
    assert doc["status"] == "done"
    assert doc["method"] == "pdf_mixed"
    assert doc["extractor"] == "pdf"
    assert doc["pages_done"] == doc["pages_total"] == 3
    assert isinstance(doc["warnings"], list)  # parsed, not a JSON string
    assert any("page 2 routed to OCR" in w for w in doc["warnings"])
    assert isinstance(doc["metadata"], dict)


def test_chunks_are_ordered_and_carry_provenance(api, tmp_path):
    doc_id = api.upload(make_pdf(tmp_path / "m.pdf", [LONG, None, LONG])).json()["id"]
    chunks = api.client.get(f"/documents/{doc_id}/chunks").json()

    assert [c["idx"] for c in chunks] == [0, 1, 2]
    assert [c["page"] for c in chunks] == [1, 2, 3]
    assert [c["method"] for c in chunks] == ["pdf_text", "pdf_ocr", "pdf_text"]
    assert chunks[1]["confidence"] is not None  # only OCR'd chunks have one
    assert isinstance(chunks[0]["metadata"], dict)
    assert "metadata_json" not in chunks[0]


def test_text_has_page_markers_and_labels_ocr_pages(api, tmp_path):
    doc_id = api.upload(make_pdf(tmp_path / "m.pdf", [LONG, None, LONG])).json()["id"]
    r = api.client.get(f"/documents/{doc_id}/text")

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    text = r.text
    assert text.index("--- page 1 ---") < text.index("--- page 2 ---") < text.index("--- page 3 ---")
    assert "[mock OCR text for page 2]" in text
    assert text.count("--- page") == 3  # a marker per page, not per chunk


def test_docx_text_has_no_page_markers(api, tmp_path):
    doc_id = api.upload(make_docx(tmp_path / "d.docx")).json()["id"]
    doc = api.client.get(f"/documents/{doc_id}").json()
    assert doc["status"] == "done" and doc["method"] == "docx"

    text = api.client.get(f"/documents/{doc_id}/text").text
    assert "Title here" in text and "Body paragraph." in text
    assert "page " not in text and "None" not in text


def test_done_document_with_zero_chunks_is_200_not_404(api, tmp_path):
    doc_id = api.upload(make_docx(tmp_path / "blank.docx", paragraphs=[])).json()["id"]
    assert api.client.get(f"/documents/{doc_id}/chunks").json() == []
    assert api.client.get(f"/documents/{doc_id}/text").text == ""


# ---------- 404 vs 409 vs 200: the status contract the UI relies on ----------

@pytest.mark.parametrize("suffix", ["", "/chunks", "/text"])
def test_unknown_id_is_404_everywhere(api, suffix):
    assert api.client.get(f"/documents/does-not-exist{suffix}").status_code == 404


def test_failed_document_detail_is_200_but_content_is_409(api, tmp_path):
    txt = tmp_path / "notes.txt"
    txt.write_text("not a supported format")
    doc_id = api.upload(txt).json()["id"]

    detail = api.client.get(f"/documents/{doc_id}")
    assert detail.status_code == 200  # failure is data, not a server error
    assert detail.json()["status"] == "failed"
    assert "No extractor" in detail.json()["error"]

    for suffix in ("/chunks", "/text"):
        r = api.client.get(f"/documents/{doc_id}{suffix}")
        assert r.status_code == 409
        assert "failed" in r.json()["detail"]
        assert "No extractor" in r.json()["detail"]  # user is told WHY


@pytest.mark.parametrize("status", ["queued", "routing", "extracting"])
def test_in_progress_document_is_pollable_and_content_is_409(api, status):
    """The UI polls GET /documents/{id}. It must return progress while processing."""
    con = connect(api.db_path)
    with con:
        con.execute(
            "INSERT INTO documents (id, filename, size, sha256, storage_path, status, pages_done, pages_total)"
            " VALUES ('p1', 'x.pdf', 1, 'h', '/srv/secret/p1', ?, 2, 5)", (status,))
    con.close()

    detail = api.client.get("/documents/p1")
    assert detail.status_code == 200
    assert (detail.json()["status"], detail.json()["pages_done"], detail.json()["pages_total"]) == (status, 2, 5)
    for suffix in ("/chunks", "/text"):
        r = api.client.get(f"/documents/p1{suffix}")
        assert r.status_code == 409 and status in r.json()["detail"]


# ---------- security / API-shape ----------

def test_storage_path_and_raw_json_columns_never_leak(api, tmp_path):
    doc_id = api.upload(make_pdf(tmp_path / "a.pdf", [LONG])).json()["id"]
    responses = [
        api.client.get(f"/documents/{doc_id}").json(),
        api.client.get("/documents").json(),
        api.client.get(f"/documents/{doc_id}/chunks").json(),
    ]
    blob = json.dumps(responses)
    assert "storage_path" not in blob
    assert "warnings_json" not in blob and "metadata_json" not in blob
    assert str(api.upload_dir) not in blob  # no server paths in any value either


def test_client_filename_cannot_escape_upload_dir(api, tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", [LONG])
    r = api.upload(pdf, filename="../../evil.pdf")
    assert r.status_code == 202

    assert api.client.get(f"/documents/{r.json()['id']}").json()["filename"] == "evil.pdf"
    on_disk = list(api.upload_dir.iterdir())
    assert len(on_disk) == 1 and on_disk[0].name == r.json()["id"]  # named by uuid
    assert not (tmp_path.parent / "evil.pdf").exists()


def test_extension_is_not_trusted(api, tmp_path):
    """A PDF named .docx is still routed as a PDF (sniffed from bytes)."""
    doc_id = api.upload(make_pdf(tmp_path / "a.pdf", [LONG]), filename="report.docx").json()["id"]
    doc = api.client.get(f"/documents/{doc_id}").json()
    assert doc["extractor"] == "pdf" and doc["status"] == "done"


# ---------- upload validation + cleanup ----------

def test_empty_upload_is_400_and_leaves_nothing_behind(api):
    r = api.upload(b"", filename="empty.pdf")
    assert r.status_code == 400
    assert list(api.upload_dir.iterdir()) == []
    assert api.client.get("/documents").json() == []


def test_oversize_upload_is_413_and_cleans_up_partial_file(api, monkeypatch):
    monkeypatch.setattr(main, "MAX_BYTES", 100)
    monkeypatch.setattr(main, "CHUNK_SIZE", 10)  # force several writes before the limit trips
    r = api.upload(b"x" * 500, filename="big.pdf")
    assert r.status_code == 413
    assert list(api.upload_dir.iterdir()) == []  # partial file removed
    assert api.client.get("/documents").json() == []  # no orphan row


def test_corrupt_pdf_fails_gracefully_not_500(api):
    r = api.upload(b"%PDF-1.4 this is not really a pdf", filename="bad.pdf")
    assert r.status_code == 202  # upload itself succeeded
    doc = api.client.get(f"/documents/{r.json()['id']}").json()
    assert doc["status"] == "failed" and doc["error"]


# ---------- listing ----------

def test_list_is_newest_first_and_paginated(api, tmp_path):
    ids = [api.upload(make_docx(tmp_path / f"{i}.docx", [f"doc {i}"])).json()["id"] for i in range(3)]

    listed = api.client.get("/documents").json()
    assert [d["id"] for d in listed] == ids[::-1]  # newest first, even within the same second
    assert {"id", "filename", "status", "pages_done", "pages_total", "method", "created_at"} == set(listed[0])

    page = api.client.get("/documents?limit=2&offset=1").json()
    assert [d["id"] for d in page] == ids[::-1][1:3]


@pytest.mark.parametrize("query", ["limit=0", "limit=9999", "offset=-1"])
def test_list_rejects_bad_pagination(api, query):
    assert api.client.get(f"/documents?{query}").status_code == 422
