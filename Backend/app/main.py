import logging
import hashlib
import os
from pathlib import Path
from uuid import uuid4
from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile, Query
from contextlib import asynccontextmanager
import json
import sqlite3
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.db import connect, init_db
from app.core.pipeline import process_document
from app.extractors import register_defaults


DB_PATH = os.environ.get("DB_PATH", "data/app.db")
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "data/uploads"))
MAX_BYTES = 25 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024
log = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once at startup, before any request is served
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    init_db(DB_PATH)
    register_defaults()  # without this the router has no extractors
    yield

app = FastAPI(title="Doc extraction", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # the Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

def save_upload(file: UploadFile, dest: Path) -> tuple[int, str]:
    hasher = hashlib.sha256()
    size = 0
    with open(dest, "wb") as out: 
        while chunk := file.file.read(CHUNK_SIZE):
            size += len(chunk)
            if size > MAX_BYTES: 
                raise HTTPException(status_code=413, detail="File too large")
            out.write(chunk)
            hasher.update(chunk)
    if size == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    return size, hasher.hexdigest()

def doc_to_dict(row) -> dict:
    d = dict(row)
    d.pop("storage_path", None)
    d["warnings"] = json.loads(d.pop("warnings_json"))
    d["metadata"] = json.loads(d.pop("metadata_json"))
    return d
    
def chunk_to_dict(row) -> dict:
    d = dict(row)
    d["metadata"] = json.loads(d.pop("metadata_json"))
    return d

def get_doc_or_404(con, doc_id: str) -> sqlite3.Row:
    row = con.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return row


def require_done(row: sqlite3.Row) -> None:
    status = row["status"]
    if status == "done":
        return
    if status == "failed":
        detail = f"Document processing failed: {row['error']}"
    else:
        detail = f"Document is not ready yet (status: {status})"
    raise HTTPException(status_code=409, detail=detail)


@app.post("/documents", status_code=202)
def upload_document(file: UploadFile, background_tasks: BackgroundTasks):
    doc_id = str(uuid4())
    dest_path = UPLOAD_DIR / doc_id 
    display_name = Path(file.filename or "unnamed").name 
 
    try:
        size, sha256 = save_upload(file, dest_path)
        con = connect(DB_PATH)
        try:
            with con:  # commits on success, rolls back on error
                con.execute(
                    "INSERT INTO documents (id, filename, size, sha256, storage_path)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (doc_id, display_name, size, sha256, str(dest_path)),
                )
        finally:
            con.close()
    except Exception as e:
        dest_path.unlink(missing_ok=True)  # any failure -> no orphan file
        if isinstance(e, HTTPException):
            raise
        log.exception("failed to store upload %s", doc_id)
        raise HTTPException(status_code=500, detail="Failed to store document") from e
    background_tasks.add_task(process_document, DB_PATH, doc_id)
    return {"id": doc_id, "status": "queued"}

@app.get("/documents")
def list_documents(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    con = connect(DB_PATH)
    try:
        rows = con.execute(
            "SELECT id, filename, status, pages_done, pages_total, method, created_at"
            " FROM documents ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        con.close()


@app.get("/documents/{doc_id}")
def get_document_by_id(doc_id: str):
    con = connect(DB_PATH)
    try:
        return doc_to_dict(get_doc_or_404(con, doc_id))
    finally:
        con.close()


@app.get("/documents/{doc_id}/chunks")
def get_document_chunks(doc_id: str):
    con = connect(DB_PATH)
    try:
        require_done(get_doc_or_404(con, doc_id))
        rows = con.execute(
            "SELECT * FROM chunks WHERE document_id = ? ORDER BY idx", (doc_id,)
        ).fetchall()
        return [chunk_to_dict(row) for row in rows]
    finally:
        con.close()


@app.get("/documents/{doc_id}/text")
def get_document_text(doc_id: str):
    con = connect(DB_PATH)
    try:
        require_done(get_doc_or_404(con, doc_id))
        rows = con.execute(
            "SELECT text, page FROM chunks WHERE document_id = ? ORDER BY idx", (doc_id,)
        ).fetchall()
        parts: list[str] = []
        current_page = None
        for row in rows:
            if row["page"] is not None and row["page"] != current_page:
                current_page = row["page"]
                parts.append(f"--- page {current_page} ---")
            parts.append(row["text"])
        return PlainTextResponse("\n\n".join(parts))
    finally:
        con.close()