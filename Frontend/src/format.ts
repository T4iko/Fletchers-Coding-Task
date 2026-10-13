/** SQLite's datetime('now') is UTC but has no timezone marker ("2026-10-11 14:03:22").
 *  `new Date()` would read that as LOCAL time and be hours off, so mark it as UTC first. */
export function formatDate(sqliteUtc: string): string {
  const date = new Date(sqliteUtc.replace(' ', 'T') + 'Z');
  return Number.isNaN(date.getTime()) ? sqliteUtc : date.toLocaleString();
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}