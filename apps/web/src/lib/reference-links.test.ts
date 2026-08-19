/**
 * The reference tabs are nothing but links and prose, so the only things that
 * can be wrong are: a link that goes nowhere useful, a link with no
 * description, or a description in one language and not the other.
 *
 * All three are silent failures — the tab still renders, it is just subtly
 * useless — which is exactly the sort this project tests for.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

import * as links from './reference-links.ts';

const here = dirname(fileURLToPath(import.meta.url));
const i18n = join(here, '..', 'i18n');
const en = JSON.parse(readFileSync(join(i18n, 'en.json'), 'utf-8'));
const hi = JSON.parse(readFileSync(join(i18n, 'hi.json'), 'utf-8'));

/**
 * Every exported link list, discovered rather than listed.
 *
 * The first version named three arrays by hand. Four more groups were added
 * later — inputs, rentals, buyers, credit — and none of them were added here,
 * so four whole tabs shipped with no domain check, no https check and no
 * description check at all. The test passed the entire time.
 *
 * Reading the module's exports means a new group is covered the moment it
 * exists, and `test_every_group_is_covered` fails if that ever stops being
 * true.
 */
const GROUP_OF: Record<string, string> = {
  PSL_LINKS: 'psl',
  SCHEME_LINKS: 'schemes',
  EMANDI_LINKS: 'emandi',
  INPUT_LINKS: 'inputs',
  RENTAL_LINKS: 'rental',
  BUYER_LINKS: 'buyers',
  CREDIT_APPLY_LINKS: 'credit',
};

const EXPORTED_LISTS = Object.entries(links).filter(
  ([, value]) => Array.isArray(value) && value.every((item) => item && typeof item.url === 'string'),
) as [string, { key: string; url: string; authority: string }[]][];

const ALL = EXPORTED_LISTS.flatMap(([name, list]) =>
  list.map((link) => ({ ...link, group: GROUP_OF[name] ?? name })),
);

test('every exported link list is covered by these tests', () => {
  // Guards the guard. A new group added to reference-links.ts without a name
  // here would otherwise be silently excluded from every check below.
  const uncovered = EXPORTED_LISTS.map(([name]) => name).filter((name) => !GROUP_OF[name]);
  assert.deepEqual(uncovered, [], 'new link group is not covered by the link tests');
  assert.ok(EXPORTED_LISTS.length >= 7, `only found ${EXPORTED_LISTS.length} link lists`);
});

test('every link has a description in both languages', () => {
  // A missing key renders as the raw key — "psl.items.kcc" — on the page.
  const missing: string[] = [];
  for (const link of ALL) {
    for (const [name, dictionary] of [['en', en], ['hi', hi]] as const) {
      const text = dictionary[link.group]?.items?.[link.key];
      if (!text) missing.push(`${name}: ${link.group}.items.${link.key}`);
    }
  }
  assert.deepEqual(missing, []);
});

test('every description has a matching link', () => {
  // The other direction: prose describing a link that was removed leaves a
  // paragraph pointing at nothing.
  const keys = new Set(ALL.map((link) => `${link.group}.${link.key}`));
  const orphans: string[] = [];
  for (const group of Object.values(GROUP_OF)) {
    for (const key of Object.keys(en[group]?.items ?? {})) {
      if (!keys.has(`${group}.${key}`)) orphans.push(`${group}.items.${key}`);
    }
  }
  assert.deepEqual(orphans, []);
});

test('every link is https and points at a government or RBI domain', () => {
  // These tabs exist to send a farmer to an authority. A link to anywhere else
  // would inherit the credibility of the ones beside it without earning it.
  const allowed = /\.(gov\.in|nic\.in)$|\.org\.in$|^(www\.)?rbi\.org\.in$|^(www\.)?nabard\.org$/;

  // Official, but on a bare .in rather than .gov.in — so it is named here
  // instead of loosening the pattern for every .in domain. Verified: the site
  // is "JanSamarth - National Portal for Government Sponsored Schemes", the
  // Government of India's single window for scheme-linked credit.
  //
  // SFAC is likewise on a .com: verified from the site itself, which states it
  // is a "Society promoted by Department of Agriculture and Farmers Welfare,
  // Ministry of Agriculture and Farmers Welfare, Govt. of India".
  const ALLOWED_BY_NAME = new Set(['www.jansamarth.in', 'sfacindia.com']);
  const bad: string[] = [];
  for (const link of ALL) {
    const url = new URL(link.url);
    assert.equal(url.protocol, 'https:', `${link.key} is not https`);
    if (!allowed.test(url.hostname) && !ALLOWED_BY_NAME.has(url.hostname)) {
      bad.push(`${link.key}: ${url.hostname}`);
    }
  }
  assert.deepEqual(bad, [], 'non-official domain in the reference tabs');
});

test('every link names the authority that publishes it', () => {
  // It is what makes the link checkable rather than merely blue.
  for (const link of ALL) {
    assert.ok(link.authority && link.authority.length > 3, `${link.key} has no authority`);
  }
});

test('no duplicate links', () => {
  const urls = ALL.map((link) => link.url);
  assert.equal(new Set(urls).size, urls.length);
});

test('the credit tab quotes no interest rate or loan limit', () => {
  // Rates change by bank, state and year. A stale one presented as current is
  // the same failure as a fabricated MSP — and it would contradict the chat,
  // which refuses loan questions three tabs away.
  for (const [name, dictionary] of [['en', en], ['hi', hi]] as const) {
    const prose = JSON.stringify(dictionary.psl ?? {});
    assert.ok(!/\d+(\.\d+)?\s*%/.test(prose), `${name}: psl tab quotes a percentage`);
    assert.ok(!/₹\s?\d/.test(prose), `${name}: psl tab quotes a rupee figure`);
  }
});
