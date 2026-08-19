import { ApiError } from './api-error';

/**
 * Falling back to recorded data when the network is gone.
 *
 * WHAT THIS DOES NOT DO
 * ---------------------
 * It does not compute anything. There is no agronomy, no economics and no unit
 * conversion here, and there must never be — architecture.md calls the frontend
 * boundary "the single most important in the system", because it means exactly
 * one place can produce a wrong number.
 *
 * So an offline answer is not a second implementation of the ranker. It is a
 * RECORDING of a real one: the fixtures under public/fixtures/generated are
 * responses this API actually produced, per district and per season, written by
 * scripts/generate_mock_fixtures.py. Serving one offline replays an answer; it
 * does not invent one.
 *
 * WHAT IT COSTS THE FARMER TO KNOW
 * --------------------------------
 * A recording is not current. Prices move, and the recording was made for a
 * 1 ha plot. Both facts are attached to the response as warnings rather than
 * left for the reader to infer, and the UI shows them at the top. An offline
 * answer that looks identical to a live one would be the dishonest version of
 * this feature.
 */

/** Only a failure to REACH the server may fall back. A 422 is a real answer. */
function isReachabilityFailure(error: unknown): boolean {
  return error instanceof ApiError && error.isRecoverableOffline;
}

/**
 * The browser's own view of connectivity.
 *
 * Deliberately not trusted as proof of anything. `navigator.onLine` only means
 * a network interface exists — a phone showing one bar of GPRS with no route to
 * the internet reports true. It is used to explain a failure that has already
 * happened, never to decide whether to try.
 */
export function isBrowserOffline(): boolean {
  return typeof navigator !== 'undefined' && navigator.onLine === false;
}

/**
 * Marker attached to any response served from a recording.
 *
 * Added because the first version of this was silent. A slow Earth Engine
 * cold start exceeded the 15-second field-summary timeout, the fallback fired,
 * and the farmer was shown recorded soil and rainfall for a district with
 * nothing anywhere to say so — the satellite service was working, merely slow.
 *
 * A substitution the reader cannot detect is the worst outcome this codebase
 * can produce, so every fallback now says what it did.
 */
export interface MaybeRecorded {
  offline_recording?: boolean;
}

/**
 * Try the network; on a reachability failure, replay a recording.
 *
 * Attempts the live call FIRST, always. A cached answer is a consolation, not
 * a shortcut, and a farmer on a working connection should never be handed a
 * recording because we guessed their signal was poor.
 */
export async function withOfflineFallback<T>(
  live: () => Promise<T>,
  recorded: () => Promise<T>,
): Promise<T> {
  try {
    return await live();
  } catch (error) {
    if (!isReachabilityFailure(error)) throw error;

    try {
      const result = await recorded();
      if (result && typeof result === 'object') {
        (result as MaybeRecorded).offline_recording = true;
      }
      return result;
    } catch {
      // No recording for this district or season either. Re-throw the ORIGINAL
      // network error: "could not reach the server" is the true and useful
      // message, and it is what the retry button responds to.
      throw error;
    }
  }
}
