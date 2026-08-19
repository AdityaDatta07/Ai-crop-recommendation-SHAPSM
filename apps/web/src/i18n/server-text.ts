import { interpolate, lookup, MESSAGES, type Locale } from './index';

/**
 * Renders prose that the API generated.
 *
 * THE PROBLEM
 * -----------
 * Warnings, reasons, comparison verdicts and price explanations are written by
 * the server, which speaks English. Switching the app to Hindi translated the
 * headings around them and left the sentences themselves in English — so a
 * farmer reading Hindi got Hindi labels wrapped around English advice, which is
 * the half that actually matters.
 *
 * WHY NOT TRANSLATE ON THE SERVER
 * -------------------------------
 * It would need a second copy of these dictionaries living in Python. Two
 * copies drift, and the one that drifts is always the one nobody is looking at.
 *
 * WHAT HAPPENS INSTEAD
 * --------------------
 * The server sends a stable `code` plus the `params` that belong in the
 * sentence. This renders it from the dictionary the app already ships. If a
 * code has no entry — a new server message against an older client — we fall
 * back to the server's English. Wrong language beats a blank space or a raw
 * key on screen, and it is honest about what happened.
 */

/**
 * Values that arrive inside params as English words rather than numbers.
 *
 * "Your canal supply is adequate" has to become "आपकी नहर आपूर्ति पर्याप्त है",
 * so the word canal needs translating too, not just the sentence around it.
 * Only closed sets belong here: things with a known, finite list of values.
 * Crop names are deliberately absent — they come from the reference data and
 * are resolved there, not guessed at here.
 */
const TERM_PARAMS = new Set([
  'source',
  'need',
  'season',
  'texture',
  'preferred',
  'factor',
  'label',
  'month',
]);

/**
 * Params that are money and must be grouped.
 *
 * interpolate() calls String(value), so 83866 rendered as "83866" while the
 * same figure elsewhere on the page read "₹83,866" — one number, two formats,
 * one screen. Formatting has to happen before substitution because the
 * dictionary only holds a placeholder.
 */
// harvest_price / other_price are quintal prices from the crowding panel.
// Without them here they render as "2000" beside "₹2,000" elsewhere on the
// same page — the same quantity formatted two ways, which reads as two
// different numbers.
const MONEY_PARAMS = new Set([
  'amount', 'price', 'cost', 'margin', 'msp', 'gap', 'harvest_price', 'other_price',
]);

const money = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });

function translateTerm(locale: Locale, value: string): string {
  const key = `server.term.${value.toLowerCase().trim()}`;
  const translated = lookup(MESSAGES[locale], key);
  return translated === key ? value : translated;
}

/** Comma lists ("loam, sandy loam") translate element by element. */
function translateTermList(locale: Locale, value: string): string {
  return value
    .split(',')
    .map((part) => translateTerm(locale, part))
    .join(', ');
}

export type ServerTextGroup =
  | 'chat'
  | 'reason'
  | 'warning'
  | 'verdict'
  | 'outlook'
  | 'counterfactual'
  | 'crowding';

function tryLookup(locale: Locale, key: string): string | null {
  const value = lookup(MESSAGES[locale], key);
  return value === key ? null : value;
}

/**
 * Crop names are not in these dictionaries on purpose — they live in
 * data/reference/crops.yaml, which already carries name_hi, and copying them
 * here would create a second list to keep in step.
 *
 * Instead the server sends `{param}_code` next to any crop-name param, and the
 * caller passes the code -> localised name map it already has from the crops
 * endpoint. No match means we keep the English name the server sent, which is
 * still true.
 */
function resolveCropNames(
  values: Record<string, string | number>,
  params: Record<string, unknown>,
  cropNames: Record<string, string> | undefined,
): void {
  if (!cropNames) return;
  for (const [name, raw] of Object.entries(params)) {
    if (!name.endsWith('_code') || typeof raw !== 'string' || raw === '') continue;
    const target = name.slice(0, -'_code'.length);
    if (!(target in values)) continue;
    // Comma-joined for list params like the unpriced-crops warning.
    const resolved = raw
      .split(',')
      .map((code) => cropNames[code.trim().toUpperCase()])
      .filter((n): n is string => Boolean(n));
    if (resolved.length > 0) values[target] = resolved.join(', ');
  }
}

export function renderServerText(
  locale: Locale,
  group: ServerTextGroup,
  code: string | undefined,
  params: Record<string, unknown> | undefined,
  fallback: string,
  cropNames?: Record<string, string>,
): string {
  if (!code) return fallback;

  // Minimal plural rule: one vs many, keyed off `places`. Both languages here
  // need it ("one place" / "3 places"), and "1 place(s)" on a farmer's printout
  // reads like a bug. Anything more elaborate can wait for a language that
  // needs it.
  const key = `server.${group}.${code}`;
  const singular = params?.places === 1;
  const template = tryLookup(locale, singular ? `${key}_one` : key) ?? tryLookup(locale, key);
  if (template === null) return fallback; // No translation for this code.

  const values: Record<string, string | number> = {};
  for (const [name, raw] of Object.entries(params ?? {})) {
    if (raw === null || raw === undefined) continue;
    if (typeof raw === 'number') {
      values[name] = MONEY_PARAMS.has(name) ? money.format(raw) : raw;
    } else if (TERM_PARAMS.has(name)) {
      values[name] = translateTermList(locale, String(raw));
    } else {
      values[name] = String(raw);
    }
  }

  resolveCropNames(values, params ?? {}, cropNames);

  return interpolate(template, values);
}
