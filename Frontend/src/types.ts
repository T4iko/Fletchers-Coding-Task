export type Status = 'queued' | 'routing' | 'extracting' | 'done' | 'failed';

export interface DocSummary {            // GET /documents
  id: string; filename: string; status: Status;
  pages_done: number; pages_total: number | null;
  method: string | null; created_at: string;
}
export interface DocDetail extends DocSummary {   // GET /documents/{id}
  mime: string | null; size: number; sha256: string;
  extractor: string | null; warnings: string[];
  metadata: Record<string, unknown>;
  error: string | null; finished_at: string | null;
}
export interface Chunk {                 // GET /documents/{id}/chunks
  id: number; document_id: string; idx: number;
  page: number | null;
  type: 'paragraph' | 'heading' | 'table' | 'page';
  text: string; method: string | null; confidence: number | null;
  metadata: Record<string, unknown>;
}