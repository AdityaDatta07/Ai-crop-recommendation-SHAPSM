import en from './en.json';
import hi from './hi.json';
import mr from './mr.json';
import bn from './bn.json';
import gu from './gu.json';
import ta from './ta.json';
import te from './te.json';

/**
 * Order matters — it is the order of the buttons in the switcher, and
 * roughly the order of speaker numbers among the states this app covers.
 */
export const LOCALES = ['en', 'hi', 'mr', 'bn', 'gu', 'ta', 'te'] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = 'en';

/**
 * en.json is the source of truth for the key set. Typing the dictionaries
 * against it means a key missing from hi.json is a compile error, not a
 * string that silently renders in the wrong language at a demo.
 */
export type Messages = typeof en;

export const MESSAGES: Record<Locale, Messages> = {
  en,
  hi: hi as Messages,
  mr: mr as Messages,
  bn: bn as Messages,
  gu: gu as Messages,
  ta: ta as Messages,
  te: te as Messages,
};

/**
 * Each language named in its own script, never in English.
 *
 * A farmer who cannot read the current language has to be able to find their
 * own in the switcher. "Tamil" written in Latin is no help to someone who
 * reads only Tamil; "தமிழ்" is.
 */
export const LOCALE_NAMES: Record<Locale, string> = {
  en: 'English',
  hi: 'हिन्दी',
  mr: 'मराठी',
  bn: 'বাংলা',
  gu: 'ગુજરાતી',
  ta: 'தமிழ்',
  te: 'తెలుగు',
};

function raw(messages: Messages, key: string): string | null {
  const value = key
    .split('.')
    .reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], messages);
  return typeof value === 'string' ? value : null;
}

/**
 * Dot path into the message tree, e.g. "crop.expectedYield".
 *
 * A KEY MISSING FROM A LANGUAGE FALLS BACK TO ENGLISH, NOT TO THE KEY PATH
 * ------------------------------------------------------------------------
 * This used to return the key itself, on the reasoning that a visible
 * "crop.expectedYield" is obvious in review. That held while there were two
 * languages and both were complete. With seven it is actively dangerous: a
 * farmer reading Telugu would get a dotted identifier in the middle of a
 * sentence, in Latin script, with no way to guess what it meant.
 *
 * English is not a good answer either — it is just a much better one. A
 * farmer who can read some English gets the meaning; one who cannot at least
 * sees a real sentence and knows to switch language rather than assuming the
 * app is broken. The i18n tests fail on any missing key, so this is a safety
 * net rather than a licence to leave gaps.
 */
export function lookup(messages: Messages, key: string): string {
  return raw(messages, key) ?? raw(MESSAGES.en, key) ?? key;
}

/** Replaces {name} placeholders. Deliberately minimal - no plurals yet. */
export function interpolate(template: string, values?: Record<string, string | number>): string {
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in values ? String(values[name]) : match,
  );
}
