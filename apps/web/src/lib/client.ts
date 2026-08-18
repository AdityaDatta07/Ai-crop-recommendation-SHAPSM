import {
  API_BASE_URL,
  FIELD_SUMMARY_TIMEOUT_MS,
  INDICES_TIMEOUT_MS,
  REQUEST_TIMEOUT_MS,
  USE_MOCK_API,
} from './config';
import { ApiError } from './api-error';
import { mockApi } from './mock';
import type {
  CropsResponse,
  DistrictsResponse,
  FieldSummaryRequest,
  FieldSummaryResponse,
  IndicesRequest,
  IndicesResponse,
  Lang,
  RecommendationRequest,
  RecommendationResponse,
} from '@/types/api';

interface RequestOptions {
  method?: 'GET' | 'POST';
  body?: unknown;
  timeoutMs?: number;
  lang?: Lang;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, timeoutMs = REQUEST_TIMEOUT_MS, lang } = options;

  const url = new URL(`${API_BASE_URL}${path}`);
  if (lang) url.searchParams.set('lang', lang);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(url.toString(), {
      method,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (error) {
    clearTimeout(timer);
    if (error instanceof DOMException && error.name === 'AbortError') throw ApiError.timeout();
    throw ApiError.network();
  }
  clearTimeout(timer);

  // Contract section 5: X-Request-Id is set on every response. Always log it.
  const requestId = response.headers.get('X-Request-Id');
  if (requestId) console.debug(`[api] ${method} ${path} -> ${response.status} (${requestId})`);

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    if (!response.ok) {
      throw new ApiError(
        { code: 'INTERNAL_ERROR', message: `Server returned ${response.status}.` },
        response.status,
      );
    }
    throw new ApiError({ code: 'INTERNAL_ERROR', message: 'Malformed response.' }, response.status);
  }

  if (!response.ok) {
    if (ApiError.isEnvelope(payload)) throw new ApiError(payload.error, response.status);
    throw new ApiError(
      { code: 'INTERNAL_ERROR', message: `Server returned ${response.status}.` },
      response.status,
    );
  }

  return payload as T;
}

export const api = {
  getDistricts(): Promise<DistrictsResponse> {
    if (USE_MOCK_API) return mockApi.districts();
    return request<DistrictsResponse>('/api/v1/meta/districts');
  },

  getCrops(lang?: Lang): Promise<CropsResponse> {
    if (USE_MOCK_API) return mockApi.crops();
    return request<CropsResponse>('/api/v1/meta/crops', { lang });
  },

  getFieldSummary(body: FieldSummaryRequest): Promise<FieldSummaryResponse> {
    if (USE_MOCK_API) return mockApi.fieldSummary(body.location);
    return request<FieldSummaryResponse>('/api/v1/geo/field-summary', {
      method: 'POST',
      body,
      timeoutMs: FIELD_SUMMARY_TIMEOUT_MS,
    });
  },

  getIndices(body: IndicesRequest): Promise<IndicesResponse> {
    if (USE_MOCK_API) return mockApi.indices(body.location);
    return request<IndicesResponse>('/api/v1/geo/indices', {
      method: 'POST',
      body,
      timeoutMs: INDICES_TIMEOUT_MS,
    });
  },

  postRecommendations(body: RecommendationRequest, lang?: Lang): Promise<RecommendationResponse> {
    if (USE_MOCK_API) return mockApi.recommendations(body);
    return request<RecommendationResponse>('/api/v1/recommendations', {
      method: 'POST',
      body,
      lang,
    });
  },

  getRecommendationById(requestId: string): Promise<RecommendationResponse> {
    if (USE_MOCK_API) return mockApi.recommendationById(requestId);
    return request<RecommendationResponse>(
      `/api/v1/recommendations/${encodeURIComponent(requestId)}`,
    );
  },
};
