import { useRef, useState } from 'react';
import type { ChangeEvent, CSSProperties, DragEvent, KeyboardEvent } from 'react';
import { uploadDocument } from '../api';

interface DropZoneProps {
  onUploaded: () => void; // parent passes `refresh`, so the list updates after uploads
}

export default function DropZone({ onUploaded }: DropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [failures, setFailures] = useState<string[]>([]);

  async function handleFiles(files: File[]) {
    if (uploading || files.length === 0) return; // ignore drops while a batch is in flight

    setFailures([]);
    setUploading(true);
    try {
      // allSettled waits for EVERY upload and reports each outcome,
      // so one bad file can't hide the results of the others.
      const results = await Promise.allSettled(files.map((f) => uploadDocument(f)));

      const failed: string[] = [];
      results.forEach((result, i) => {
        if (result.status === 'rejected') {
          const reason = result.reason instanceof Error ? result.reason.message : 'Upload failed';
          failed.push(`${files[i].name}: ${reason}`); // results keep the same order as `files`
        }
      });
      setFailures(failed);
    } finally {
      setUploading(false);
      onUploaded();
    }
  }

  function onDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault(); // REQUIRED: without this the browser never fires `drop`
    setDragging(true);
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault(); // REQUIRED: stops the browser from opening the file in the tab
    setDragging(false);
    handleFiles(Array.from(e.dataTransfer.files)); // FileList is not an array
  }

  function onInputChange(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = ''; // lets the user pick the same file again later
    handleFiles(files);
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      inputRef.current?.click(); // keyboard users can open the picker too
    }
  }

  return (
    <>
      <div
        role="button"
        tabIndex={0}
        aria-busy={uploading}
        onClick={() => inputRef.current?.click()}
        onKeyDown={onKeyDown}
        onDragOver={onDragOver}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        style={{
          ...boxStyle,
          borderColor: dragging ? '#2563eb' : '#999',
          background: dragging ? '#eff6ff' : 'transparent',
          opacity: uploading ? 0.6 : 1,
        }}
      >
        {uploading ? 'Uploading...' : 'Drop files here, or click to choose'}
        <input ref={inputRef} type="file" multiple hidden onChange={onInputChange} />
      </div>

      {failures.length > 0 && (
        <ul role="alert" style={failureStyle}>
          {failures.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}
    </>
  );
}

const boxStyle: CSSProperties = {
  border: '2px dashed #999',
  borderRadius: '8px',
  padding: '2rem',
  textAlign: 'center',
  cursor: 'pointer',
  margin: '1rem 0',
};
const failureStyle: CSSProperties = { color: '#b00020', margin: '0 0 1rem', paddingLeft: '1.25rem' };