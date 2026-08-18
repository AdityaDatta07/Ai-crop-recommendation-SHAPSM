/**
 * Compile-time contract check.
 *
 * The fixtures in data/seed/api-fixtures are what the frontend is built against
 * and what apps/api must eventually return. This file asserts they still match
 * the types in src/types/api.ts. It produces no runtime output: if a fixture
 * drifts from the contract, `npm run typecheck` fails and CI catches it.
 */
import crops from '../../../../data/seed/api-fixtures/meta.crops.json';
import districts from '../../../../data/seed/api-fixtures/meta.districts.json';
import fieldSummary from '../../../../data/seed/api-fixtures/geo.field-summary.json';
import success from '../../../../data/seed/api-fixtures/recommendations.success.json';
import lowConfidence from '../../../../data/seed/api-fixtures/recommendations.low-confidence.json';
import noData from '../../../../data/seed/api-fixtures/recommendations.error-no-data.json';

import type {
  ApiErrorEnvelope,
  CropsResponse,
  DistrictsResponse,
  FieldSummaryResponse,
  RecommendationResponse,
} from '@/types/api';

/**
 * TypeScript widens string literals when importing JSON, so `"rabi"` arrives as
 * `string` and would fail against `Season`. Widen<T> relaxes exactly that, and
 * nothing else: missing keys, extra nesting, wrong primitive types and null vs
 * number mistakes all still fail. Tuple lengths are relaxed to arrays.
 */
type Widen<T> = T extends string
  ? string
  : T extends number
    ? number
    : T extends boolean
      ? boolean
      : T extends null
        ? null
        : T extends readonly (infer U)[]
          ? Widen<U>[]
          : T extends object
            ? { [K in keyof T]: Widen<T[K]> }
            : T;

// Each assignment is the assertion. No casts - if a fixture is wrong, this file
// stops compiling.
const _crops: Widen<CropsResponse> = crops;
const _districts: Widen<DistrictsResponse> = districts;
const _fieldSummary: Widen<FieldSummaryResponse> = fieldSummary;
const _success: Widen<RecommendationResponse> = success;
const _lowConfidence: Widen<RecommendationResponse> = lowConfidence;
const _noData: Widen<ApiErrorEnvelope> = noData;

export const CONTRACT_FIXTURES = {
  crops: _crops,
  districts: _districts,
  fieldSummary: _fieldSummary,
  success: _success,
  lowConfidence: _lowConfidence,
  noData: _noData,
};
