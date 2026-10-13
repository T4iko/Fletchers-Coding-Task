-- Original file is stored on disk (storage_path); this DB holds metadata + extracted content.
CREATE TABLE IF NOT EXISTS documents (
    id            TEXT PRIMARY KEY,                 -- uuid4
    filename      TEXT NOT NULL,
    mime          TEXT,                             -- sniffed from bytes, not trusted from client
    size          INTEGER NOT NULL,
    sha256        TEXT NOT NULL,                    -- dedupe + OCR cache key
    storage_path  TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'queued'
                  CHECK (status IN ('queued','routing','extracting','done','failed')),
    extractor     TEXT,                             -- registry name, e.g. 'pdf'
    method        TEXT,                             -- 'pdf_text' | 'pdf_ocr' | 'pdf_mixed' | 'docx'
    pages_total   INTEGER,
    pages_done    INTEGER NOT NULL DEFAULT 0,
    warnings_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    error         TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents(sha256);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);

CREATE TABLE IF NOT EXISTS chunks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id   TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    idx           INTEGER NOT NULL,                 -- reading order within document
    page          INTEGER,                          -- 1-based; NULL for formats without pages
    type          TEXT NOT NULL,                    -- paragraph | heading | table | page
    text          TEXT NOT NULL,
    method        TEXT,                             -- per-chunk provenance (mixed PDFs)
    confidence    REAL,                             -- OCR confidence if applicable
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE (document_id, idx)
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_page ON chunks(document_id, page);

-- Full-text search (external-content FTS5, kept in sync by triggers)
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, content='chunks', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;

--cache OCR output per (file hash, page) so re-runs and duplicate uploads cost nothing.
CREATE TABLE IF NOT EXISTS ocr_cache (
    sha256     TEXT NOT NULL,
    page       INTEGER NOT NULL,
    provider   TEXT NOT NULL,
    text       TEXT NOT NULL,
    confidence REAL,
    PRIMARY KEY (sha256, page, provider)
);
