import { MOCK_SCENARIO, type MockScenario } from './config';
import { ApiError } from './api-error';
import type {
  CropsResponse,
  DistrictsResponse,
  FieldSummaryResponse,
  IndicesResponse,
  Location,
  LonLat,
  RecommendationRequest,
  RecommendationResponse,
} from '@/types/api';

/**
 * Mock transport.
 *
 * This used to replay a single hardcoded response, which meant picking Nagpur
 * showed Lucknow's soil and rabi crops. It lied, quietly, in the one mode we
 * were most likely to demo in.
 *
 * It now serves per-district, per-season recordings of the REAL API, produced by
 * scripts/generate_mock_fixtures.py. Two consequences worth keeping:
 *
 *  - There is still exactly one implementation of the agronomy, in services/ml.
 *    This file looks fixtures up; it does not rank, score or calculate anything.
 *  - When the ranker changes, re-run the generator and the mock changes with it.
 *    A stale mock is a wrong mock.
 */

const AREA_RECORDED_HA = 1.0;

async function fixture<T>(name: string): Promise<T | null> {
  const res = await fetch(`/fixtures/${name}.json`, { cache: 'force-cache' });
  if (!res.ok) return null;
  return (await res.json()) as T;
}

async function requiredFixture<T>(name: string): Promise<T> {
  const data = await fixture<T>(name);
  if (data === null) throw ApiError.network();
  return data;
}

/** Latency the real path has, so loading states get exercised in dev. */
function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ---------------------------------------------------------------- location

function haversineKm([lon1, lat1]: LonLat, [lon2, lat2]: LonLat): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const R = 6371;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function ringCentroid(coordinates: LonLat[][]): LonLat {
  const outer = coordinates[0] ?? [];
  const points =
    outer.length > 1 && outer[0][0] === outer[outer.length - 1][0] ? outer.slice(0, -1) : outer;
  const lon = points.reduce((sum, p) => sum + p[0], 0) / points.length;
  const lat = points.reduce((sum, p) => sum + p[1], 0) / points.length;
  return [lon, lat];
}

/**
 * Resolve any location form to a district code, mirroring what services/geo
 * does server-side. Needed so coordinates and drawn fields work in mock mode
 * rather than silently falling back to one default district.
 */
async function resolveDistrictCode(location: Location): Promise<string | null> {
  if (location.type === 'admin') return location.district_code;

  const point: LonLat =
    location.type === 'point'
      ? [location.lon, location.lat]
      : ringCentroid(location.geometry.coordinates);

  const districts = await requiredFixture<DistrictsResponse>('meta.districts');
  let best: { code: string; distance: number } | null = null;

  for (const state of districts.states) {
    for (const district of state.districts) {
      const distance = haversineKm(point, district.centroid);
      if (best === null || distance < best.distance) {
        best = { code: district.district_code, distance };
      }
    }
  }

  // Same 150 km coverage limit the backend applies, so mock mode fails the
  // same way live does instead of snapping to a district 500 km away.
  return best && best.distance <= 150 ? best.code : null;
}

// ------------------------------------------------------------------ scenarios

function forcedScenario(): MockScenario | null {
  return MOCK_SCENARIO === 'success' ? null : MOCK_SCENARIO;
}

/** Says plainly that these numbers are a recording, not a live calculation.
 *
 * Two callers, two different things to say. In mock MODE a developer chose to
 * replay fixtures. In offline FALLBACK a farmer lost signal and we replayed one
 * on their behalf, which is a different situation and deserves different words.
 */
function mockWarnings(requestedAreaHa: number, offline = false) {
  const warnings = [
    offline
      ? {
          code: 'OFFLINE_RECORDING',
          params: {},
          message:
            'You are offline. This is a recorded result for this district and season, ' +
            'not a live calculation — prices in particular may have moved. Reconnect for ' +
            'current figures.',
        }
      : {
          code: 'MOCK_DATA',
          params: {},
          message:
            'Offline sample data — a recording of a real result for this district and season, ' +
            'not a live calculation. Connect the API for current figures.',
        },
  ];

  // The recording is for a 1 ha plot. Rescaling it here would mean doing
  // economics in the frontend, which is the one thing this app must never do,
  // so we say so instead of quietly showing the wrong plot size.
  if (Math.abs(requestedAreaHa - AREA_RECORDED_HA) > 0.001) {
    warnings.push({
      code: 'MOCK_FIXED_AREA',
      params: { recorded: AREA_RECORDED_HA, requested: requestedAreaHa },
      message:
        `Sample figures are for a ${AREA_RECORDED_HA} ha plot, not the ` +
        `${requestedAreaHa} ha you entered. Connect the API to size them to your field.`,
    });
  }

  return warnings;
}

export const mockApi = {
  async districts(): Promise<DistrictsResponse> {
    await delay(120);
    return requiredFixture<DistrictsResponse>('meta.districts');
  },

  async crops(): Promise<CropsResponse> {
    await delay(120);
    return requiredFixture<CropsResponse>('meta.crops');
  },

  async fieldSummary(location: Location): Promise<FieldSummaryResponse> {
    await delay(700);

    const districtCode = await resolveDistrictCode(location);
    if (districtCode === null) {
      throw new ApiError(
        {
          code: 'NO_DATA_FOR_LOCATION',
          message: 'No coverage for that location. Try a point inside a supported district.',
          field: 'location',
        },
        422,
      );
    }

    const recorded = await fixture<FieldSummaryResponse>(
      `generated/field-summary.${districtCode}`,
    );
    if (recorded) return recorded;

    return requiredFixture<FieldSummaryResponse>('geo.field-summary');
  },

  async indices(location: Location): Promise<IndicesResponse> {
    await delay(500);
    const districtCode = await resolveDistrictCode(location);
    if (districtCode === null) {
      throw new ApiError(
        { code: 'NO_DATA_FOR_LOCATION', message: 'No coverage for that location.', field: 'location' },
        422,
      );
    }
    const recorded = await fixture<IndicesResponse>(`generated/indices.${districtCode}`);
    if (recorded) return recorded;
    throw new ApiError(
      { code: 'UPSTREAM_FAILED', message: 'No recorded imagery for this district.' },
      502,
    );
  },

  async recommendations(
    request: RecommendationRequest,
    offline = false,
  ): Promise<RecommendationResponse> {
    // No artificial latency when standing in for a dead network: the farmer has
    // already waited for the request to time out.
    await delay(offline ? 0 : 1600);

    const scenario = forcedScenario();
    if (scenario === 'error-no-data') {
      const body = await requiredFixture<{ error: { code: string; message: string } }>(
        'recommendations.error-no-data',
      );
      throw new ApiError(body.error, 422);
    }
    if (scenario === 'low-confidence') {
      return requiredFixture<RecommendationResponse>('recommendations.low-confidence');
    }

    const districtCode = await resolveDistrictCode(request.location);
    if (districtCode === null) {
      const body = await requiredFixture<{ error: { code: string; message: string } }>(
        'recommendations.error-no-data',
      );
      throw new ApiError(body.error, 422);
    }

    const recorded = await fixture<RecommendationResponse>(
      `generated/recommendations.${districtCode}.${request.season}`,
    );

    if (!recorded) {
      throw new ApiError(
        {
          code: 'UNSUPPORTED_SEASON',
          message: `No crops are calendared for the ${request.season} season in this district.`,
          field: 'season',
        },
        400,
      );
    }

    // Honour exclusions client-side. This is filtering, not ranking - ranks are
    // renumbered but no score is recomputed.
    let recommendations = recorded.recommendations;
    const excluded = new Set((request.constraints?.exclude_crops ?? []).map((c) => c.toUpperCase()));
    if (excluded.size > 0) {
      recommendations = recommendations
        .filter((item) => !excluded.has(item.crop_code))
        .map((item, index) => ({ ...item, rank: index + 1 }));
    }
    if (request.limit) {
      recommendations = recommendations.slice(0, request.limit);
    }

    return {
      ...recorded,
      recommendations,
      warnings: [...recorded.warnings, ...mockWarnings(request.area_ha, offline)],
    };
  },

  async recommendationById(requestId: string): Promise<RecommendationResponse> {
    await delay(300);
    const data = await requiredFixture<RecommendationResponse>('recommendations.success');
    return { ...data, request_id: requestId };
  },
};
