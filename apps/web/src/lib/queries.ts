'use client';

import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from './client';
import { readResult, saveResult } from './cache';
import { ApiError } from './api-error';
import type {
  FieldSummaryRequest,
  Location,
  RecommendationRequest,
  RecommendationResponse,
} from '@/types/api';

/** Reference lists change rarely - contract section 4 says cache aggressively. */
const REFERENCE_STALE_MS = 24 * 60 * 60 * 1000;

export function useDistricts() {
  return useQuery({
    queryKey: ['meta', 'districts'],
    queryFn: () => api.getDistricts(),
    staleTime: REFERENCE_STALE_MS,
  });
}

export function useCrops() {
  return useQuery({
    queryKey: ['meta', 'crops'],
    queryFn: () => api.getCrops(),
    staleTime: REFERENCE_STALE_MS,
  });
}

/** Fires as soon as a location is chosen, before the farmer commits to a run. */
export function useFieldSummary(location: Location | null) {
  return useQuery({
    queryKey: ['geo', 'field-summary', location],
    queryFn: () => api.getFieldSummary({ location } as FieldSummaryRequest),
    enabled: location !== null,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
}

/** Called on every boundary edit, so it is debounced by the caller. */
export function useIndices(location: Location | null) {
  return useQuery({
    queryKey: ['geo', 'indices', location],
    queryFn: () => api.getIndices({ location: location as Location }),
    enabled: location !== null,
    retry: false,
    staleTime: 30 * 60 * 1000,
  });
}

export function useRecommendations() {
  return useMutation<RecommendationResponse, ApiError, RecommendationRequest>({
    mutationFn: (request) => api.postRecommendations(request),
    onSuccess: (data) => saveResult(data),
    retry: false,
  });
}

/**
 * Deep links and refreshes. Cache first so a saved result renders instantly and
 * still works with no network; the network call only fills gaps.
 */
export function useRecommendationById(requestId: string) {
  return useQuery({
    queryKey: ['recommendations', requestId],
    queryFn: async () => {
      const cached = readResult(requestId);
      if (cached) return cached;
      const fresh = await api.getRecommendationById(requestId);
      saveResult(fresh);
      return fresh;
    },
    enabled: Boolean(requestId),
    retry: false,
    staleTime: Infinity,
  });
}
