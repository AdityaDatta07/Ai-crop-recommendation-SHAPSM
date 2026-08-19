/**
 * Run with: npm test (in apps/web)
 *
 * The failure these guard against is not a crash. It is a spoken advisory that
 * quietly disagrees with the page it was read from — which nobody can catch by
 * looking, because you cannot look at a voice.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { advisoryScript, joinScript, renderPart, type AdvisoryInput } from './advisory-speech.ts';

const name = (_code: string, fallback: string) => fallback;

function result(overrides: Partial<AdvisoryInput> = {}): AdvisoryInput {
  return {
    location_resolved: { district_name: 'Lucknow', area_ha: 1 },
    recommendations: [
      { rank: 1, crop_code: 'WHEAT', name: 'Wheat', confidence: 'high', economics: { net_margin: 45000 } },
      { rank: 2, crop_code: 'GRAM', name: 'Chickpea', confidence: 'medium', economics: { net_margin: 31000 } },
      { rank: 3, crop_code: 'MUSTARD', name: 'Mustard', confidence: 'medium', economics: { net_margin: 22000 } },
      { rank: 4, crop_code: 'BARLEY', name: 'Barley', confidence: 'low', economics: { net_margin: 12000 } },
    ],
    warnings: [],
    ...overrides,
  };
}

const keys = (input: AdvisoryInput) => advisoryScript(input, name).map((p) => p.key);

// ------------------------------------------------------------------ contents

test('the place is named before any crop', () => {
  // Otherwise a farmer who half-hears the start does not know whose field this
  // is about, and this app will happily report a district it only guessed at.
  assert.equal(keys(result())[0], 'voice.place');
});

test('only the top three crops are spoken', () => {
  const spoken = advisoryScript(result(), name).filter((p) => p.key === 'voice.crop');
  assert.equal(spoken.length, 3);
  assert.deepEqual(
    spoken.map((p) => p.params?.crop),
    ['Wheat', 'Chickpea', 'Mustard'],
  );
});

test('the ranks spoken are the ranks on the page', () => {
  const spoken = advisoryScript(result(), name).filter((p) => p.key === 'voice.crop');
  assert.deepEqual(spoken.map((p) => p.params?.rank), [1, 2, 3]);
});

test('crop names go through the translator', () => {
  const hindi = advisoryScript(result(), () => 'गेहूँ');
  const first = hindi.find((p) => p.key === 'voice.crop');
  assert.equal(first?.params?.crop, 'गेहूँ');
});

// -------------------------------------------------------------------- money

test('money is spoken as a plain grouped number, not a currency symbol', () => {
  // A synthesiser reading "₹45,000" may say "R forty five thousand", or skip
  // the symbol entirely. The word "rupees" belongs in the sentence.
  const money = advisoryScript(result(), name).find((p) => p.key === 'voice.money');
  assert.equal(money?.params?.amount, '45,000');
  assert.equal(String(money?.params?.amount).includes('₹'), false);
});

test('money is quoted for the crop it belongs to', () => {
  // "About 45,000 rupees" with no crop attached is the kind of number that
  // gets remembered against whichever crop was mentioned last.
  const money = advisoryScript(result(), name).find((p) => p.key === 'voice.money');
  assert.equal(money?.params?.crop, 'Wheat');
});

test('a part-hectare plot is not rounded to a whole one', () => {
  // Most plots in this country are under a hectare. Sharing the money
  // formatter (0 decimals) would say "your 1 hectare plot" while the rupee
  // figure in the same sentence was computed on 0.81 — one sentence
  // contradicting itself, spoken aloud, with nothing on screen to catch it.
  const small = result({ location_resolved: { district_name: 'Lucknow', area_ha: 0.81 } });
  const money = advisoryScript(small, name).find((p) => p.key === 'voice.money');
  assert.equal(money?.params?.area, '0.81');
});

test('money still drops the paise', () => {
  const odd = result({
    recommendations: [
      { rank: 1, crop_code: 'WHEAT', name: 'Wheat', confidence: 'high', economics: { net_margin: 45123.67 } },
    ],
  });
  const money = advisoryScript(odd, name).find((p) => p.key === 'voice.money');
  assert.equal(money?.params?.amount, '45,124');
});

test('an unpriced crop is not given a spoken figure', () => {
  const unpriced = result({
    recommendations: [
      { rank: 1, crop_code: 'ONION', name: 'Onion', confidence: 'high', economics: { net_margin: null } },
    ],
  });
  assert.equal(keys(unpriced).includes('voice.money'), false);
});

// ----------------------------------------------------------------- warnings

test('warnings are always spoken when the page has them', () => {
  // The single most important property in this file. A listener who is told
  // the ranking but not the caution has been told less than the page says.
  const warned = result({ warnings: [{ code: 'sowing_window_closed' }, { code: 'provisional' }] });
  assert.equal(keys(warned).includes('voice.warnings'), true);
});

test('warnings are spoken last', () => {
  const warned = result({ warnings: [{ code: 'x' }, { code: 'y' }] });
  const spoken = keys(warned);
  assert.equal(spoken[spoken.length - 1], 'voice.warnings');
});

test('one warning is not announced as plural', () => {
  const warned = result({ warnings: [{ code: 'only' }] });
  assert.equal(keys(warned).includes('voice.warningsOne'), true);
  assert.equal(keys(warned).includes('voice.warnings'), false);
});

test('the spoken count matches the number of warnings', () => {
  const warned = result({ warnings: [{ code: 'a' }, { code: 'b' }, { code: 'c' }] });
  const part = advisoryScript(warned, name).find((p) => p.key === 'voice.warnings');
  assert.equal(part?.params?.count, 3);
});

test('no warnings means no warning sentence', () => {
  assert.equal(keys(result()).includes('voice.warnings'), false);
  assert.equal(keys(result()).includes('voice.warningsOne'), false);
});

// -------------------------------------------------------------- empty result

test('an empty result still says something', () => {
  // Pressing listen and hearing silence reads as a broken button, and the
  // farmer waits for an answer that is never coming.
  const empty = result({ recommendations: [] });
  assert.equal(keys(empty).includes('voice.empty'), true);
});

test('an empty result with warnings still speaks the warnings', () => {
  const empty = result({ recommendations: [], warnings: [{ code: 'no_data' }] });
  assert.equal(keys(empty).includes('voice.warningsOne'), true);
});

// ------------------------------------------------------------------- joining

test('parts are joined with spaces', () => {
  assert.equal(joinScript(['One.', 'Two.']), 'One. Two.');
});

// ------------------------------------------------------------- translation

test('confidence is emitted as a key, never as a bare word', () => {
  // "high" spoken inside a Hindi sentence is an English word a Hindi voice
  // mispronounces. The page never had this bug because the badge translates
  // separately — which is exactly why the voice could acquire it unnoticed.
  const part = advisoryScript(result(), name).find((p) => p.key === 'voice.crop');
  assert.equal(part?.params?.confidence, undefined);
  assert.equal(part?.paramKeys?.confidence, 'crop.high');
});

test('the confidence key is the one the badge already uses', () => {
  const parts = advisoryScript(result(), name).filter((p) => p.key === 'voice.crop');
  assert.deepEqual(
    parts.map((p) => p.paramKeys?.confidence),
    ['crop.high', 'crop.medium', 'crop.medium'],
  );
});

test('renderPart resolves key-valued params before substituting', () => {
  const dictionary: Record<string, string> = {
    'crop.high': 'ऊँचा',
    'voice.crop': 'Number {rank}: {crop}. Confidence {confidence}.',
  };
  const t = (key: string, params?: Record<string, string | number>) =>
    (dictionary[key] ?? key).replace(/\{(\w+)\}/g, (_, k) => String(params?.[k] ?? `{${k}}`));

  const part = advisoryScript(result(), name).find((p) => p.key === 'voice.crop')!;
  assert.equal(renderPart(part, t), 'Number 1: Wheat. Confidence ऊँचा.');
});

test('renderPart leaves a part with no paramKeys alone', () => {
  const t = (key: string, params?: Record<string, string | number>) =>
    `${key}:${JSON.stringify(params ?? {})}`;
  assert.equal(renderPart({ key: 'voice.empty' }, t), 'voice.empty:{}');
});
