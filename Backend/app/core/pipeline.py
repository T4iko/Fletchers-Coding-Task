"""Orchestrator: queued -> routing -> extracting -> done | failed.
Idempotent: re-running a document replaces its chunks, so it is safe to retry
or to re-extract when an extractor improves (we keep the original file)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.extractors import registry
from app.extractors.base import DocumentInfo, ExtractionError
from app.extractors.sniff import sniff_mime

from .db import connect

log = logging.getLogger(__name__)


def process_document(db_path: str, doc_id: str) -> None:
    con = connect(db_path)
    try:
        row = con.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        path = Path(row["storage_path"])

        _update(con, doc_id, status="routing")
        info = DocumentInfo(path=path, filename=row["filename"], mime=sniff_mime(path),
                            size=row["size"], sha256=row["sha256"])
        extractor = registry.route(info)
        _update(con, doc_id, status="extracting", mime=info.mime, extractor=extractor.name)

        def on_progress(done: int, total: int) -> None:
            _update(con, doc_id, pages_done=done, pages_total=total)

        result = extractor.extract(info, on_progress)

        with con:  # single transaction: chunks + final status land together
            con.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
            con.executemany(
                "INSERT INTO chunks (document_id, idx, page, type, text, method, confidence, metadata_json)"
                " VALUES (?,?,?,?,?,?,?,?)",
                [(doc_id, i, c.page, c.type, c.text, c.method, c.confidence, json.dumps(c.metadata))
                 for i, c in enumerate(result.chunks)],
            )
            con.execute(
                "UPDATE documents SET status='done', method=?, warnings_json=?, metadata_json=?,"
                " error=NULL, finished_at=datetime('now') WHERE id=?",
                (result.method, json.dumps(result.warnings), json.dumps(result.metadata), doc_id),
            )
    except ExtractionError as e:  # expected: show message to user
        _update(con, doc_id, status="failed", error=str(e), finished_at="now")
    except Exception as e:  # unexpected: log with traceback, generic message to user
        log.exception("pipeline crashed for %s", doc_id)
        _update(con, doc_id, status="failed", error=f"Internal error: {type(e).__name__}", finished_at="now")
    finally:
        con.close()


_COLUMNS = {"status", "mime", "extractor", "pages_done", "pages_total", "error", "finished_at"}


def _update(con, doc_id: str, **fields) -> None:
    assert set(fields) <= _COLUMNS
    if fields.get("finished_at") == "now":
        fields["finished_at"] = None
        sets = ", ".join(f"{k}=?" for k in fields if k != "finished_at") + ", finished_at=datetime('now')"
        vals = [v for k, v in fields.items() if k != "finished_at"]
    else:
        sets = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values())
    with con:
        con.execute(f"UPDATE documents SET {sets} WHERE id=?", (*vals, doc_id))
