import type { Status } from './types';

/** Statuses where the backend is still working: keep polling while any of these. */
export const ACTIVE_STATUSES: Status[] = ['queued', 'routing', 'extracting'];