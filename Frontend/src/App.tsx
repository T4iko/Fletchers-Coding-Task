import { useCallback, useEffect, useState } from 'react';
import type { CSSProperties } from 'react';
import { listDocuments } from './api';
import DocumentDetail from './components/DocumentDetail';
import DropZone from './components/Dropzone';
import { formatDate } from './format';
import { ACTIVE_STATUSES } from './status';
import type { DocSummary } from './types';

const POLL_MS = 1000;

export default function App() {
  const [documents, setDocuments] = useState<DocSummary[]>([]);
  const [loading, setLoading] = useState(true); // true only until the FIRST load finishes
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setDocuments(await listDocuments());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load documents');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // A boolean, not the array: the polling effect below restarts only when this FLIPS,
  // not every time a poll returns new data.
  const hasActive = documents.some((d) => ACTIVE_STATUSES.includes(d.status));

  useEffect(() => {
    if (!hasActive) return; // nothing in progress -> no timer at all

    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;

    // Chained setTimeout, not setInterval: the next poll is scheduled only AFTER the
    // previous one finishes, so slow responses can never overlap or arrive out of order.
    async function tick() {
      await refresh();
      if (!stopped) timer = setTimeout(tick, POLL_MS);
    }
    timer = setTimeout(tick, POLL_MS);

    return () => {
      stopped = true; // cleanup: effect re-ran, component unmounted, or work finished
      clearTimeout(timer);
    };
  }, [hasActive, refresh]);

  return (
    <main style={pageStyle}>
      <h1>Documents</h1>

      <DropZone onUploaded={refresh} />

      {error && <p role="alert" style={errorStyle}>Error: {error}</p>}

      {loading ? (
        <p>Loading documents...</p>
      ) : documents.length === 0 ? (
        !error && <p>No documents yet. Upload a file to get started.</p>
      ) : (
        <table style={tableStyle}>
          <thead>
            <tr>
              <th style={cellStyle}>Filename</th>
              <th style={cellStyle}>Status</th>
              <th style={cellStyle}>Method</th>
              <th style={cellStyle}>Uploaded</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => (
              <tr
                key={doc.id}
                tabIndex={0}
                onClick={() => setSelectedId(doc.id)}
                onKeyDown={(e) => e.key === 'Enter' && setSelectedId(doc.id)}
                style={{ cursor: 'pointer', background: doc.id === selectedId ? '#f3f4f6' : undefined }}
              >
                <td style={cellStyle}>{doc.filename}</td>
                <td style={cellStyle}>
                  {doc.status}
                  {ACTIVE_STATUSES.includes(doc.status) && (
                    <div>
                      <progress
                        max={doc.pages_total ?? undefined}
                        value={doc.pages_total ? doc.pages_done : undefined}
                        aria-label={`Processing ${doc.filename}`}
                      />{' '}
                      <small>
                        {doc.pages_total ? `${doc.pages_done}/${doc.pages_total}` : 'waiting…'}
                      </small>
                    </div>
                  )}
                </td>
                <td style={cellStyle}>{doc.method ?? '—'}</td>
                <td style={cellStyle}>{formatDate(doc.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {selectedId && (
        // key={selectedId}: switching documents remounts the panel, so no stale state leaks across
        <DocumentDetail key={selectedId} id={selectedId} onClose={() => setSelectedId(null)} />
      )}
    </main>
  );
}

const pageStyle: CSSProperties = { padding: '2rem', maxWidth: '900px', margin: '0 auto' };
const tableStyle: CSSProperties = { width: '100%', borderCollapse: 'collapse', textAlign: 'left' };
const cellStyle: CSSProperties = { padding: '12px', borderBottom: '1px solid #ddd', verticalAlign: 'top' };
const errorStyle: CSSProperties = { color: '#b00020' };