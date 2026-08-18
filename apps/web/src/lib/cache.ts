import type { RecommendationResponse } from '@/types/api';

/**
 * Offline replay, per architecture.md principle 4.
 *
 * localStorage for now: synchronous, no schema, enough for the last handful of
 * results. api-contract.md section 4 calls for IndexedDB, which is the right
 * home once the service worker lands - swap this module's internals then and
 * nothing above it changes.
 */

const RESULT_PREFIX = 'crop:result:';
const LAST_KEY = 'crop:last-request-id';
const MAX_STORED = 10;

function available(): boolean {
  return typeof window !== 'undefined' && !!window.localStorage;
}

export function saveResult(result: RecommendationResponse): void {
  if (!available()) return;
  try {
    localStorage.setItem(RESULT_PREFIX + result.request_id, JSON.stringify(result));
    localStorage.setItem(LAST_KEY, result.request_id);
    prune();
  } catch {
    // Quota or private mode. Caching is a convenience, never a requirement.
  }
}

export function readResult(requestId: string): RecommendationResponse | null {
  if (!available()) return null;
  try {
    const raw = localStorage.getItem(RESULT_PREFIX + requestId);
    return raw ? (JSON.parse(raw) as RecommendationResponse) : null;
  } catch {
    return null;
  }
}

export function readLastResult(): RecommendationResponse | null {
  if (!available()) return null;
  const id = localStorage.getItem(LAST_KEY);
  return id ? readResult(id) : null;
}

function prune(): void {
  const keys = Object.keys(localStorage).filter((k) => k.startsWith(RESULT_PREFIX));
  if (keys.length <= MAX_STORED) return;
  const sorted = keys
    .map((key) => {
      const raw = localStorage.getItem(key);
      let generatedAt = '';
      try {
        generatedAt = raw ? (JSON.parse(raw) as RecommendationResponse).generated_at : '';
      } catch {
        /* drop unparseable entries first */
      }
      return { key, generatedAt };
    })
    .sort((a, b) => a.generatedAt.localeCompare(b.generatedAt));

  for (const { key } of sorted.slice(0, sorted.length - MAX_STORED)) {
    localStorage.removeItem(key);
  }
}
