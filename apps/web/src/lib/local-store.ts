/**
 * Saved plans and the season diary, kept on this device.
 *
 * WHY LOCAL AND NOT AN ACCOUNT
 * ----------------------------
 * Accounts mean auth, sessions, an ownership model and a password-reset path a
 * farmer can actually complete — the week of work deferred as Point 21. Local
 * storage gives most of the value today at none of that cost.
 *
 * IT ALSO CHANGES WHAT WE MAY PROMISE, AND THE UI SAYS SO
 * -------------------------------------------------------
 * "Saved" normally means "kept somewhere safe". Here it means "kept in this
 * browser on this phone". Clear the browser data, switch to a different phone,
 * or open the app in private mode, and everything is gone. A farmer who logged
 * three seasons of yields and lost them would be right to be angry, so both
 * panels say plainly where the data lives rather than letting the word "saved"
 * carry an implication it cannot honour.
 *
 * WHY THE ADVISORY ITSELF IS NOT STORED
 * -------------------------------------
 * A saved plan holds the request id and a few fields to show in a list. The
 * advisory stays on the server, fetched fresh when opened. Storing a copy would
 * mean a farmer reading last month's prices in a layout identical to today's,
 * with nothing to tell them apart — the same substitution problem the offline
 * recording banner exists to prevent.
 */

const PLANS_KEY = 'beej-nirnay.saved-plans.v1';
const DIARY_KEY = 'beej-nirnay.season-diary.v1';

/** Beyond this the list stops being browsable and starts being a database. */
export const MAX_PLANS = 50;

export interface SavedPlan {
  requestId: string;
  /** What the farmer called this field. Their words, not ours. */
  label: string;
  districtName: string;
  season: string;
  areaHa: number;
  topCrop: string;
  topCropCode: string;
  savedAt: string;
}

export interface DiaryEntry {
  id: string;
  requestId: string;
  /** What they actually sowed, which may not be what was recommended. */
  cropSown: string;
  sownOn: string;
  /** Filled in months later, if at all. */
  harvestedOn?: string;
  yieldQuintal?: number | null;
  soldPricePerQuintal?: number | null;
  notes?: string;
  updatedAt: string;
}

function read<T>(key: string): T[] {
  // Private browsing throws on access in some browsers rather than returning
  // null, so this has to be guarded rather than checked.
  try {
    if (typeof window === 'undefined') return [];
    const raw = window.localStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch {
    return [];
  }
}

function write<T>(key: string, value: T[]): boolean {
  try {
    if (typeof window === 'undefined') return false;
    window.localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    // Quota exceeded, or storage disabled. Returning false rather than
    // throwing lets the caller tell the farmer it did not save, which is the
    // one thing worse than not saving: saying it saved when it did not.
    return false;
  }
}

export function storageAvailable(): boolean {
  try {
    if (typeof window === 'undefined') return false;
    const probe = '__beej_probe__';
    window.localStorage.setItem(probe, '1');
    window.localStorage.removeItem(probe);
    return true;
  } catch {
    return false;
  }
}

// ------------------------------------------------------------- saved plans

export function loadPlans(): SavedPlan[] {
  return read<SavedPlan>(PLANS_KEY).sort((a, b) => b.savedAt.localeCompare(a.savedAt));
}

export function savePlan(plan: SavedPlan): boolean {
  const existing = loadPlans().filter((p) => p.requestId !== plan.requestId);
  // Newest first, oldest dropped past the cap.
  return write(PLANS_KEY, [plan, ...existing].slice(0, MAX_PLANS));
}

export function removePlan(requestId: string): boolean {
  return write(
    PLANS_KEY,
    loadPlans().filter((plan) => plan.requestId !== requestId),
  );
}

export function isPlanSaved(requestId: string): boolean {
  return loadPlans().some((plan) => plan.requestId === requestId);
}

// ----------------------------------------------------------- season diary

export function loadDiary(requestId?: string): DiaryEntry[] {
  const all = read<DiaryEntry>(DIARY_KEY).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  return requestId ? all.filter((entry) => entry.requestId === requestId) : all;
}

export function saveDiaryEntry(entry: DiaryEntry): boolean {
  const existing = read<DiaryEntry>(DIARY_KEY).filter((e) => e.id !== entry.id);
  return write(DIARY_KEY, [entry, ...existing]);
}

export function removeDiaryEntry(id: string): boolean {
  return write(
    DIARY_KEY,
    read<DiaryEntry>(DIARY_KEY).filter((entry) => entry.id !== id),
  );
}

/**
 * Everything on this device, as a file.
 *
 * The honest answer to "local storage can vanish": let them take a copy. Also
 * the migration path if accounts ever arrive — nobody's diary has to be
 * retyped.
 */
export function exportAll(): string {
  return JSON.stringify(
    {
      exported_at: new Date().toISOString(),
      plans: loadPlans(),
      diary: loadDiary(),
    },
    null,
    2,
  );
}
