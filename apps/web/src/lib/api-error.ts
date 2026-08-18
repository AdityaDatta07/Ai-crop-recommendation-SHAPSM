import type { ApiErrorBody, ApiErrorEnvelope } from '@/types/api';

/**
 * Every failure the UI sees is one of these, including timeouts and network
 * loss, so screens never have to branch on `unknown`.
 */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly field?: string;
  readonly requestId?: string;

  constructor(body: ApiErrorBody, status: number) {
    super(body.message);
    this.name = 'ApiError';
    this.code = body.code;
    this.status = status;
    this.field = body.field;
    this.requestId = body.request_id;
  }

  static isEnvelope(value: unknown): value is ApiErrorEnvelope {
    return (
      typeof value === 'object' &&
      value !== null &&
      'error' in value &&
      typeof (value as ApiErrorEnvelope).error?.code === 'string'
    );
  }

  static timeout(): ApiError {
    return new ApiError(
      {
        code: 'TIMEOUT',
        message:
          'The server took too long to answer. Satellite data can be slow to wake up — try again.',
      },
      408,
    );
  }

  static network(): ApiError {
    return new ApiError(
      {
        code: 'NETWORK_ERROR',
        message: 'Could not reach the server. Check your connection and try again.',
      },
      0,
    );
  }

  /** Failures where a saved result is better than an error screen. */
  get isRecoverableOffline(): boolean {
    return this.code === 'NETWORK_ERROR' || this.code === 'TIMEOUT';
  }
}

/** Farmer-facing copy. Falls back to the server message, which is already plain. */
export function userMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 'NO_DATA_FOR_LOCATION':
        return 'We have no soil or weather coverage for that spot yet. Try a nearby district.';
      case 'INVALID_LOCATION':
        return 'That location could not be read. Check the coordinates or pick a district.';
      case 'RATE_LIMITED':
        return 'Too many requests just now. Wait a moment and try again.';
      case 'UPSTREAM_FAILED':
        return 'A data source is temporarily unavailable. Please try again shortly.';
      default:
        return error.message;
    }
  }
  return 'Something went wrong. Please try again.';
}
