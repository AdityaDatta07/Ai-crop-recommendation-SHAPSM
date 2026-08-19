/**
 * Guards on the two dictionaries themselves.
 *
 * WHY STATIC SCANNING RATHER THAN TYPES
 * -------------------------------------
 * `ListenResult.reason` and `AreaParse.reason` are string-literal unions, and
 * the UI turns each member into an i18n key by interpolation:
 * `t(\`voice.error.${reason}\`)`. TypeScript is perfectly happy with that — the
 * key is a string — so adding a member to either union and forgetting the
 * translation compiles, passes review, and ships. The farmer then sees the
 * literal text "voice.error.busy" on the screen.
 *
 * The same trick on the Python side (walking the source for emitted message
 * codes) has caught this three times, so it is worth having here too. These
 * tests read the source files and assert every union member has a key in BOTH
 * dictionaries.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, '..');

const en = JSON.parse(readFileSync(join(here, 'en.json'), 'utf-8'));
const hi = JSON.parse(readFileSync(join(here, 'hi.json'), 'utf-8'));

/**
 * Every language, and how complete each one has to be.
 *
 * `complete: true` means a missing key fails the build. Hindi has been
 * complete since the app had two languages and must stay that way.
 *
 * The five added later are `complete: false` — they are being filled in, and
 * `lookup()` falls back to English for anything absent. That is a deliberate
 * middle state, not an oversight: a partly translated app that falls back
 * cleanly is useful, whereas gating the whole feature on 3,310 finished
 * strings would have shipped nothing. What is NOT tolerated at any coverage
 * level is a key that does not exist in English, or a translation that drops
 * a placeholder — both are silent corruption rather than a visible gap.
 */
const LOCALES: { code: string; complete: boolean }[] = [
  { code: 'hi', complete: true },
  { code: 'mr', complete: false },
  { code: 'bn', complete: false },
  { code: 'gu', complete: false },
  { code: 'ta', complete: false },
  { code: 'te', complete: false },
];

const DICTIONARIES = Object.fromEntries(
  LOCALES.map(({ code }) => [code, JSON.parse(readFileSync(join(here, `${code}.json`), 'utf-8'))]),
);

function flatten(node: unknown, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === 'object') Object.assign(out, flatten(value, path));
    else out[path] = String(value);
  }
  return out;
}

const flatEn = flatten(en);
const flatHi = flatten(hi);

/** Pull the members out of a `type X = 'a' | 'b'` declaration. */
function unionMembers(file: string, declaration: string): string[] {
  const text = readFileSync(join(src, file), 'utf-8');
  const at = text.indexOf(declaration);
  assert.notEqual(at, -1, `${declaration} not found in ${file} — this test is now blind`);
  // To the blank line, not to the first `;`. These are discriminated unions,
  // so the first semicolon sits INSIDE `{ ok: true; transcript: string }` and
  // cutting there silently returns zero members — a guard that passes because
  // it found nothing to check.
  const end = text.indexOf('\n\n', at);
  const body = text.slice(at + declaration.length, end === -1 ? text.length : end);
  return [...body.matchAll(/'([a-z-_]+)'/g)].map((m) => m[1]);
}

// ------------------------------------------------------------------- parity

test('hindi is complete', () => {
  const missing = Object.keys(flatEn).filter((k) => !(k in flatHi));
  assert.deepEqual(missing, [], 'keys missing from hi.json');
});

test('no locale defines a key that does not exist in English', () => {
  // A key en.json does not have is a typo'd path. It renders nothing, ever,
  // in that language and nowhere else — the hardest kind of gap to spot.
  for (const { code } of LOCALES) {
    const extra = Object.keys(flatten(DICTIONARIES[code])).filter((k) => !(k in flatEn));
    assert.deepEqual(extra, [], `${code}.json has keys not in en.json`);
  }
});

test('every translated string keeps its placeholders', () => {
  // A dropped {amount} does not throw. It renders a plausible sentence with
  // the number silently gone — in a language nobody on the team reads.
  const placeholders = (value: string) =>
    [...value.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join();

  for (const { code } of LOCALES) {
    const flat = flatten(DICTIONARIES[code]);
    const broken = Object.keys(flat).filter(
      (key) => key in flatEn && placeholders(flat[key]) !== placeholders(flatEn[key]),
    );
    assert.deepEqual(broken, [], `${code}.json changes placeholders`);
  }
});

test('coverage is reported so a gap is a known quantity', () => {
  // Not a pass/fail on completeness — a floor, so coverage cannot silently
  // regress. Raise these as translations land.
  const total = Object.keys(flatEn).length;
  const floors: Record<string, number> = { hi: 100, mr: 20, bn: 10, gu: 20, ta: 0, te: 0 };
  for (const { code } of LOCALES) {
    const have = Object.keys(flatten(DICTIONARIES[code])).length;
    const percent = Math.round((have / total) * 100);
    assert.ok(
      percent >= floors[code],
      `${code} coverage fell to ${percent}% (floor ${floors[code]}%, ${have}/${total})`,
    );
  }
});

test('a translated string uses the same placeholders as the original', () => {
  // A dropped {amount} does not throw. It renders the sentence with a hole in
  // it, or worse, a plausible sentence with the number silently gone.
  const placeholders = (value: string) =>
    [...value.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

  const mismatched = Object.keys(flatEn)
    .filter((k) => k in flatHi)
    .filter(
      (k) => placeholders(flatEn[k]).join() !== placeholders(flatHi[k]).join(),
    );
  assert.deepEqual(mismatched, []);
});

/**
 * Deliberately identical in both files.
 *
 * The language switcher names each language in ITS OWN language — "English"
 * and "हिन्दी" — so that somebody who cannot read the current one can still
 * find their way out. Translating "English" into Hindi would defeat that.
 */
const SAME_IN_BOTH_ON_PURPOSE = new Set([
  // The switcher names each language in its own script so somebody who cannot
  // read the current one can still find their way out. Translating "English"
  // into Tamil would defeat exactly that.
  'language.english',
  'language.hindi',
  // A placeholder-only template has nothing to translate.
  'season.areaEquals',
]);

test('no translation is left as the English string', () => {
  // Excludes strings with nothing to translate: bare placeholders, numbers,
  // and punctuation-only separators.
  const suspicious = Object.keys(flatEn).filter((k) => {
    if (SAME_IN_BOTH_ON_PURPOSE.has(k)) return false;
    const value = flatEn[k];
    if (flatHi[k] !== value) return false;
    return /[a-zA-Z]{4,}/.test(value.replace(/\{\w+\}/g, ''));
  });
  assert.deepEqual(suspicious, []);
});

// ------------------------------------------------- every union member is said

test('every speech failure reason has a message in both languages', () => {
  const reasons = unionMembers('lib/speech.ts', 'export type ListenResult =');
  // 'no-speech' is swallowed by the UI: it covers silence and cancelling,
  // neither of which deserves a red message. Everything else must be sayable.
  const shown = reasons.filter((r) => r !== 'no-speech' && r !== 'true' && r !== 'false');
  assert.ok(shown.length >= 4, `only found ${shown.join(', ')} — the scan may have broken`);

  for (const reason of shown) {
    assert.ok(`voice.error.${reason}` in flatEn, `en.json has no voice.error.${reason}`);
    assert.ok(`voice.error.${reason}` in flatHi, `hi.json has no voice.error.${reason}`);
  }
});

test('every area parse failure has a message in both languages', () => {
  const reasons = unionMembers('lib/voice-parse.ts', 'export type AreaParse =');
  assert.ok(reasons.includes('ambiguous_unit'), 'the scan may have broken');

  for (const reason of reasons) {
    assert.ok(`voice.area.${reason}` in flatEn, `en.json has no voice.area.${reason}`);
    assert.ok(`voice.area.${reason}` in flatHi, `hi.json has no voice.area.${reason}`);
  }
});

// ------------------------------------------------ the spoken script resolves

test('every key the spoken advisory can emit exists', () => {
  const text = readFileSync(join(src, 'lib/advisory-speech.ts'), 'utf-8');
  const keys = [...text.matchAll(/key: '([\w.]+)'/g)].map((m) => m[1]);
  // Plus the confidence keys it builds by interpolation.
  const all = [...keys, 'crop.high', 'crop.medium', 'crop.low'];
  assert.ok(all.length >= 6, 'the scan may have broken');

  for (const key of all) {
    assert.ok(key in flatEn, `en.json has no ${key}`);
    assert.ok(key in flatHi, `hi.json has no ${key}`);
  }
});
