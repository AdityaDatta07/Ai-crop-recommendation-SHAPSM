/**
 * Run with: npm run test:web
 *
 * The parser turns speech into a plot size, and plot size turns directly into
 * rupees on the results page. A mishearing that gets believed is the failure
 * that matters, so most of these tests are about what it REFUSES to parse.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { parseArea, matchDistrict, type DistrictOption } from './voice-parse.ts';

const DISTRICTS: DistrictOption[] = [
  { district_code: 'UP-LKO', district_name: 'Lucknow' },
  { district_code: 'UP-KNP', district_name: 'Kanpur' },
  { district_code: 'MH-NGP', district_name: 'Nagpur' },
  { district_code: 'KA-BLR', district_name: 'Bengaluru' },
];

// ------------------------------------------------------------------- numbers

test('plain digits are taken as spoken', () => {
  assert.deepEqual(parseArea('2.5 hectares'), { ok: true, value: 2.5, unit: 'hectare' });
  assert.deepEqual(parseArea('3 acres'), { ok: true, value: 3, unit: 'acre' });
});

test('digits beat number words in the same sentence', () => {
  // "five" appears, but the farmer said 2. Scanning words first would return 5.
  const result = parseArea('2 hectares out of five');
  assert.equal(result.ok && result.value, 2);
});

test('english number words are understood', () => {
  const result = parseArea('two hectares');
  assert.equal(result.ok && result.value, 2);
});

test('hindi number words are understood', () => {
  const hectares = parseArea('दो हेक्टेयर');
  assert.equal(hectares.ok && hectares.value, 2);
  const acres = parseArea('तीन एकड़');
  assert.equal(acres.ok && acres.value, 3);
});

test('devanagari digits are digits', () => {
  const result = parseArea('२.५ हेक्टेयर');
  assert.equal(result.ok && result.value, 2.5);
});

test('hindi land fractions are understood', () => {
  // These are how people actually talk about land, and a word table without
  // them silently drops the utterance.
  const half = parseArea('ढाई एकड़');
  assert.equal(half.ok && half.value, 2.5);
  const oneAndHalf = parseArea('डेढ़ हेक्टेयर');
  assert.equal(oneAndHalf.ok && oneAndHalf.value, 1.5);
});

test('a fraction modifier attaches to the number after it', () => {
  // "साढ़े तीन" is three and a half, not a half and then a three.
  const threeAndHalf = parseArea('साढ़े तीन एकड़');
  assert.equal(threeAndHalf.ok && threeAndHalf.value, 3.5);
  const twoAndQuarter = parseArea('सवा दो हेक्टेयर');
  assert.equal(twoAndQuarter.ok && twoAndQuarter.value, 2.25);
});

// --------------------------------------------------------------------- units

test('a missing unit is not an error', () => {
  // The form already has a hectare/acre toggle; leave it alone.
  const result = parseArea('two and a half');
  assert.equal(result.ok, true);
  assert.equal(result.ok && result.unit, null);
});

test('bigha is refused rather than converted', () => {
  // A bigha is ~2,500 m2 in UP, 1,600 in Bengal, over 6,000 in Assam. Picking
  // one would invent the number every rupee on the results page rests on.
  const result = parseArea('do bigha');
  assert.equal(result.ok, false);
  assert.equal(!result.ok && result.reason, 'ambiguous_unit');

  const devanagari = parseArea('दो बीघा');
  assert.equal(devanagari.ok, false);
});

test('speech with no number is rejected, not defaulted', () => {
  const result = parseArea('my field is quite big');
  assert.equal(result.ok, false);
  assert.equal(!result.ok && result.reason, 'no_number');
});

test('zero and negative areas are rejected', () => {
  assert.equal(parseArea('0 hectares').ok, false);
});

// ----------------------------------------------------------------- districts

test('an exact district name matches', () => {
  assert.equal(matchDistrict('Lucknow', DISTRICTS)?.district_code, 'UP-LKO');
});

test('surrounding words do not prevent a match', () => {
  assert.equal(matchDistrict('my field is in Lucknow', DISTRICTS)?.district_code, 'UP-LKO');
  assert.equal(matchDistrict('Nagpur district', DISTRICTS)?.district_code, 'MH-NGP');
});

test('a near-miss still matches', () => {
  // What a recogniser actually returns for accented speech. Each of these is
  // two or three edits from the real name.
  assert.equal(matchDistrict('Lucknao', DISTRICTS)?.district_code, 'UP-LKO');
  assert.equal(matchDistrict('Kanpoor', DISTRICTS)?.district_code, 'UP-KNP');
  assert.equal(matchDistrict('Nagpoor', DISTRICTS)?.district_code, 'MH-NGP');
  assert.equal(matchDistrict('Bangalore', DISTRICTS)?.district_code, 'KA-BLR');
});

test('farm words near the microphone match nothing', () => {
  // The separation the threshold rests on: mishearings sit 2-3 edits away,
  // these sit 5-6. Anything in between would be a silent wrong district.
  for (const noise of ['tractor', 'wheat', 'pump', 'seed', 'hello there']) {
    assert.equal(matchDistrict(noise, DISTRICTS), null, `"${noise}" should not match`);
  }
});

test('an unrelated word matches nothing', () => {
  // The important one: a silent wrong district is a wrong soil sample, a wrong
  // rainfall figure and a wrong recommendation, none of which announce
  // themselves.
  assert.equal(matchDistrict('tractor', DISTRICTS), null);
  assert.equal(matchDistrict('hello there', DISTRICTS), null);
});

test('similar-looking districts are not confused', () => {
  assert.equal(matchDistrict('Kanpur', DISTRICTS)?.district_code, 'UP-KNP');
  assert.equal(matchDistrict('Nagpur', DISTRICTS)?.district_code, 'MH-NGP');
});

test('empty speech matches nothing', () => {
  assert.equal(matchDistrict('', DISTRICTS), null);
  assert.equal(matchDistrict('   ', DISTRICTS), null);
});
