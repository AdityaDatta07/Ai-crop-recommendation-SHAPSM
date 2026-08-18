import en from './en.json';
import hi from './hi.json';

export const LOCALES = ['en', 'hi'] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = 'en';

/**
 * en.json is the source of truth for the key set. Typing the dictionaries
 * against it means a key missing from hi.json is a compile error, not a
 * string that silently renders in the wrong language at a demo.
 */
export type Messages = typeof en;

export const MESSAGES: Record<Locale, Messages> = { en, hi: hi as Messages };

export const LOCALE_NAMES: Record<Locale, string> = {
  en: 'English',
  hi: 'हिन्दी',
};

/** Dot path into the message tree, e.g. "crop.expectedYield". */
export function lookup(messages: Messages, key: string): string {
  const value = key
    .split('.')
    .reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], messages);

  // Falling back to the key makes a missing string obvious in review rather
  // than rendering an empty element nobody notices.
  return typeof value === 'string' ? value : key;
}

/** Replaces {name} placeholders. Deliberately minimal - no plurals yet. */
export function interpolate(template: string, values?: Record<string, string | number>): string {
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in values ? String(values[name]) : match,
  );
}
