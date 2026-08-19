/**
 * Turning what somebody said into a form value.
 *
 * SCOPE, AND WHY IT IS NARROW
 * ---------------------------
 * Two fields: which district, and how big the plot is. Not a free-form
 * "describe your farm" — a recogniser that mishears a district is a nuisance,
 * but one that quietly mishears "two" as "twenty" and is believed has cost
 * somebody a season.
 *
 * So every parse either produces a value the caller shows for confirmation, or
 * returns null. Nothing is guessed at.
 *
 * BIGHA IS DELIBERATELY REFUSED
 * -----------------------------
 * It is the unit Indian farmers most often speak, and it has no fixed size: a
 * bigha is about 2,500 m2 in parts of UP, 1,600 in Bengal, 2,700 in Rajasthan
 * and over 6,000 in Assam. Converting one without knowing the district's
 * convention would invent a number, and plot size drives every rupee on the
 * results page. We say we cannot, rather than pick a value.
 */

/** Devanagari digits map to Arabic ones positionally. */
const DEVANAGARI_DIGITS = '०१२३४५६७८९';

const HINDI_NUMBERS: Record<string, number> = {
  एक: 1, दो: 2, तीन: 3, चार: 4, पांच: 5, पाँच: 5, छह: 6, छः: 6, छै: 6,
  सात: 7, आठ: 8, नौ: 9, दस: 10, ग्यारह: 11, बारह: 12, पंद्रह: 15, बीस: 20,
  // Fractions Indian speech uses constantly for land, and which a naive
  // word-to-number table would drop entirely.
  आधा: 0.5, आधी: 0.5, डेढ़: 1.5, डेढ: 1.5, ढाई: 2.5, साढ़े: 0.5, सवा: 0.25,
};

const ENGLISH_NUMBERS: Record<string, number> = {
  zero: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7,
  eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12, fifteen: 15, twenty: 20,
  half: 0.5, quarter: 0.25,
};

const HECTARE_WORDS = ['hectare', 'hectares', 'hect', 'ha', 'हेक्टेयर', 'हेक्टर'];
const ACRE_WORDS = ['acre', 'acres', 'एकड़', 'एकर'];
const BIGHA_WORDS = ['bigha', 'bighas', 'बीघा', 'बिगहा'];

export type AreaUnitSpoken = 'hectare' | 'acre';

export type AreaParse =
  | { ok: true; value: number; unit: AreaUnitSpoken | null }
  | { ok: false; reason: 'ambiguous_unit' | 'no_number' };

function normalise(text: string): string {
  let out = text.toLowerCase().trim();
  // Devanagari digits are digits; treat them as such before anything else.
  for (let i = 0; i < DEVANAGARI_DIGITS.length; i += 1) {
    out = out.split(DEVANAGARI_DIGITS[i]).join(String(i));
  }
  return out.replace(/[,।]/g, ' ').replace(/\s+/g, ' ');
}

/**
 * Find a quantity in an utterance.
 *
 * Digits win over words: somebody who says "2.5" means 2.5, and a word-scanner
 * that also finds "five" inside the sentence would produce nonsense.
 */
function findNumber(text: string): number | null {
  const digits = text.match(/\d+(?:\.\d+)?/);
  if (digits) {
    const value = Number(digits[0]);
    return Number.isFinite(value) ? value : null;
  }

  const words = text.split(' ');

  // "साढ़े तीन" is three-and-a-half, not 0.5 then 3. The modifier attaches to
  // the number that follows it, so look for that pair before single words.
  for (let i = 0; i < words.length - 1; i += 1) {
    if (words[i] === 'साढ़े' || words[i] === 'साढे') {
      const next = HINDI_NUMBERS[words[i + 1]];
      if (next !== undefined && next >= 1) return next + 0.5;
    }
    if (words[i] === 'सवा') {
      const next = HINDI_NUMBERS[words[i + 1]];
      if (next !== undefined && next >= 1) return next + 0.25;
    }
  }

  for (const word of words) {
    if (HINDI_NUMBERS[word] !== undefined) return HINDI_NUMBERS[word];
    if (ENGLISH_NUMBERS[word] !== undefined) return ENGLISH_NUMBERS[word];
  }

  return null;
}

function mentions(text: string, words: string[]): boolean {
  const padded = ` ${text} `;
  return words.some((word) => padded.includes(` ${word} `) || padded.includes(`${word} `));
}

/**
 * Parse a spoken plot size.
 *
 * A missing unit is not an error: the form already has a hectare/acre toggle,
 * so "two and a half" fills the number and leaves the toggle alone.
 */
export function parseArea(spoken: string): AreaParse {
  const text = normalise(spoken);

  if (mentions(text, BIGHA_WORDS)) {
    // See the module docstring. A bigha has no fixed size and this app turns
    // plot size directly into rupees.
    return { ok: false, reason: 'ambiguous_unit' };
  }

  const value = findNumber(text);
  if (value === null || value <= 0) return { ok: false, reason: 'no_number' };

  let unit: AreaUnitSpoken | null = null;
  if (mentions(text, HECTARE_WORDS)) unit = 'hectare';
  else if (mentions(text, ACRE_WORDS)) unit = 'acre';

  return { ok: true, value, unit };
}

// ------------------------------------------------------------------ district

/** Levenshtein, capped: we only care whether it is close, not how far. */
function distance(a: string, b: string): number {
  if (a === b) return 0;
  const rows = a.length + 1;
  const cols = b.length + 1;
  let previous = Array.from({ length: cols }, (_, i) => i);

  for (let i = 1; i < rows; i += 1) {
    const current = [i];
    for (let j = 1; j < cols; j += 1) {
      current[j] = Math.min(
        previous[j] + 1,
        current[j - 1] + 1,
        previous[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
      );
    }
    previous = current;
  }
  return previous[cols - 1];
}

export interface DistrictOption {
  district_code: string;
  district_name: string;
}

/**
 * Match an utterance against the district list.
 *
 * Returns null rather than a best-effort guess when nothing is close. A wrong
 * district silently selected is a wrong soil sample, a wrong rainfall figure
 * and a wrong recommendation, none of which announce themselves.
 */
export function matchDistrict<T extends DistrictOption>(spoken: string, districts: T[]): T | null {
  const text = normalise(spoken);
  if (!text) return null;

  let best: { option: T; score: number } | null = null;

  for (const option of districts) {
    const name = normalise(option.district_name);

    // Containment either way handles "Lucknow district" and "in Lucknow".
    if (text.includes(name) || name.includes(text)) return option;

    // Otherwise compare against each spoken word, so a stray "district" or
    // "please" does not wreck the distance.
    for (const word of text.split(' ')) {
      if (word.length < 3) continue;
      const score = distance(word, name);
      if (best === null || score < best.score) best = { option, score };
    }
  }

  if (best === null) return null;

  // Threshold set by measurement, not taste. Against this district list the
  // mishearings a recogniser actually produces — "Lucknao", "Kanpoor",
  // "Bangalore" — sit 2 to 3 edits away, while unrelated words a farmer might
  // say near the microphone ("tractor", "wheat", "pump") sit 5 to 6. Thirty
  // per cent of the name length falls in that gap.
  //
  // An earlier one-edit-per-four-characters rule allowed only 1 edit for
  // "Lucknow" and rejected "Lucknao", which is precisely the case this exists
  // to handle.
  const tolerance = Math.round(normalise(best.option.district_name).length * 0.3);
  return best.score <= Math.max(1, tolerance) ? best.option : null;
}
