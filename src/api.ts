import type { Chunk, DocDetail, DocSummary } from './types';

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, init);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : `HTTP ${res.status}`);
  }
  return res.json();
}

export const listDocuments = () => request<DocSummary[]>('/documents');
export const getDocument = (id: string) => request<DocDetail>(`/documents/${id}`);
export const getChunks = (id: string) => request<Chunk[]>(`/documents/${id}/chunks`);

export async function getText(id: string): Promise<string> {
  const res = await fetch(`${BASE}/documents/${id}/text`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.text();                      // plain text, not JSON
}

export function uploadDocument(file: File) {
  const form = new FormData();
  form.append('file', file);
  return request<{ id: string; status: string }>('/documents', { method: 'POST', body: form });
}