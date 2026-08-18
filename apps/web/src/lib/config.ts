export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, '') ?? 'http://localhost:8000';

/** Serve data/seed/api-fixtures instead of calling apps/api. */
export const USE_MOCK_API = process.env.NEXT_PUBLIC_USE_MOCK_API === 'true';

export type MockScenario = 'success' | 'low-confidence' | 'error-no-data';

export const MOCK_SCENARIO: MockScenario =
  (process.env.NEXT_PUBLIC_MOCK_SCENARIO as MockScenario) || 'success';

/**
 * api-contract.md section 3.4: Earth Engine cold start can reach 15s,
 * so the client budget is 30s with a visible progress state.
 */
export const REQUEST_TIMEOUT_MS = 30_000;
export const FIELD_SUMMARY_TIMEOUT_MS = 15_000;

/**
 * Satellite indices get their own, longer budget.
 *
 * Earth Engine cold starts run 10-15s before any work begins, and this call
 * also builds a 24-month NDVI composite. It is batched into one Earth Engine
 * request rather than 24, but it is still the slowest thing the app does.
 * At 10s it timed out every time against live Earth Engine while passing in
 * the diagnostic script — the panel is non-blocking, so waiting is fine.
 */
export const INDICES_TIMEOUT_MS = 45_000;
