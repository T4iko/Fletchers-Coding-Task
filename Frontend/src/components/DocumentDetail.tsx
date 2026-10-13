import { useEffect, useState } from 'react';
import type { CSSProperties } from 'react';
import { getChunks, getDocument } from '../api';
import { formatBytes } from '../format';
import { ACTIVE_STATUSES } from '../status';
import type { Chunk, DocDetail } from '../types';

const POLL_MS = 1000;

interface Props {
  id: string;
  onClose: () => void;
}

interface PageGroup {
  page: number | null; // null = formats without pages (DOCX)
  chunks: Chunk[];
}

/** Chunks arrive in reading order; start a new group whenever the page changes. */
function groupByPage(chunks: Chunk[]): PageGroup[] {
  const groups: PageGroup[] = [];
  for (const chunk of chunks) {
    const last = groups[groups.length - 1];
    if (last && last.page === chunk.page) last.chunks.push(chunk);
    else groups.push({ page: chunk.page, chunks: [chunk] });
  }
  return groups;
}

// The parent renders this with key={id}, so switching documents remounts it
// and all state below starts fresh.
export default function DocumentDetail({ id, onClose }: Props) {
  const [doc, setDoc] = useState<DocDetail | null>(null);
  const [chunks, setChunks] = useState<Chunk[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function load() {
      try {
        const d = await getDocument(id);
        if (cancelled) return;
        setDoc(d);
        setError(null);

        if (d.status === 'done') {
          // /chunks returns 409 until the document is done, so only ask now
          const c = await getChunks(id);
          if (!cancelled) setChunks(c);
        } else if (ACTIVE_STATUSES.includes(d.status)) {
          timer = setTimeout(load, POLL_MS);
        }
        // 'failed' is terminal: show doc.error, no chunks to fetch
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load document');
      }
    }

    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [id]);

  return (
    <section style={panelStyle} aria-label="Document detail">
      <button onClick={onClose} style={{ float: 'right' }}>Close</button>

      {error && <p role="alert" style={{ color: '#b00020' }}>Error: {error}</p>}
      {!doc && !error && <p>Loading…</p>}

      {doc && (
        <>
          <h2 style={{ marginTop: 0 }}>{doc.filename}</h2>
          <p style={metaStyle}>
            {doc.status} · extractor: {doc.extractor ?? '—'} · method: {doc.method ?? '—'} ·{' '}
            {formatBytes(doc.size)} · {doc.mime ?? 'unknown type'}
          </p>

          {doc.status === 'failed' && (
            <p role="alert" style={failedStyle}>Processing failed: {doc.error}</p>
          )}

          {ACTIVE_STATUSES.includes(doc.status) && (
            <p>
              Processing… {doc.pages_total ? `${doc.pages_done}/${doc.pages_total}` : 'waiting'}
            </p>
          )}

          {doc.warnings.length > 0 && (
            <div style={warningStyle}>
              <strong>Warnings</strong>
              <ul style={{ margin: '4px 0 0', paddingLeft: '1.25rem' }}>
                {doc.warnings.map((w) => <li key={w}>{w}</li>)}
              </ul>
            </div>
          )}

          {chunks && chunks.length === 0 && <p>No content was extracted.</p>}

          {chunks && groupByPage(chunks).map((group) => (
            <div key={group.page ?? 'all'} style={{ marginTop: '1.25rem' }}>
              <h3 style={groupHeadingStyle}>
                {group.page === null ? 'Document' : `Page ${group.page}`}
              </h3>
              {group.chunks.map((chunk) => (
                <ChunkView key={chunk.id} chunk={chunk} />
              ))}
            </div>
          ))}
        </>
      )}
    </section>
  );
}

function ChunkView({ chunk }: { chunk: Chunk }) {
  const isOcr = chunk.method === 'pdf_ocr';
  return (
    <div style={{ margin: '6px 0' }}>
      {isOcr && (
        <span style={ocrBadgeStyle}>
          OCR{chunk.confidence !== null ? ` · ${Math.round(chunk.confidence * 100)}%` : ''}
        </span>
      )}
      {chunk.type === 'heading' ? (
        <strong style={{ display: 'block' }}>{chunk.text}</strong>
      ) : (
        
        <div style={{ whiteSpace: 'pre-wrap', fontFamily: chunk.type === 'table' ? 'monospace' : 'inherit' }}>
          {chunk.text}
        </div>
      )}
    </div>
  );
}

const panelStyle: CSSProperties = { marginTop: '2rem', padding: '1.25rem', border: '1px solid #ddd', borderRadius: 8 };
const metaStyle: CSSProperties = { color: '#555', fontSize: '0.9rem' };
const failedStyle: CSSProperties = { background: '#fee2e2', color: '#b91c1c', padding: '8px 12px', borderRadius: 6 };
const warningStyle: CSSProperties = { background: '#fef9c3', color: '#854d0e', padding: '8px 12px', borderRadius: 6 };
const groupHeadingStyle: CSSProperties = { fontSize: '0.85rem', color: '#555', borderBottom: '1px solid #eee', paddingBottom: 4 };
const ocrBadgeStyle: CSSProperties = {
  display: 'inline-block', marginRight: 8, padding: '1px 8px', borderRadius: 999,
  background: '#ede9fe', color: '#5b21b6', fontSize: '0.75rem', fontWeight: 600,
};