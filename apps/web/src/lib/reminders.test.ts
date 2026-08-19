/**
 * The calendar file.
 *
 * Every failure here is silent: a malformed .ics does not error, it just fails
 * to import, or imports with the wrong date. The farmer finds out by missing
 * their sowing window.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { buildIcs, reminderEvents } from './reminders.ts';

const LABELS = {
  sow: (crop: string) => `Sowing window opens — ${crop}`,
  harvest: (crop: string) => `Harvest expected — ${crop}`,
  description: (crop: string, district: string) => `${crop} in ${district}`,
};
const name = (_code: string, fallback: string) => fallback;

function advisory(overrides: Record<string, unknown> = {}) {
  return {
    request_id: 'req_01TEST',
    location_resolved: { district_name: 'Lucknow' },
    recommendations: [
      {
        crop_code: 'LENTIL',
        name: 'Lentil',
        calendar: {
          sowing_window: { start: '2026-10-20', end: '2026-11-25' },
          harvest_window: { start: '2027-03-01', end: '2027-03-20' },
        },
      },
    ],
    ...overrides,
  } as never;
}

test('the dates come from the advisory, unaltered', () => {
  // A reminder that disagrees with the page it came from is worse than none.
  const events = reminderEvents(advisory(), LABELS, name);
  assert.deepEqual(events.map((e) => e.date), ['2026-10-20', '2027-03-01']);
});

test('only the top crop gets reminders', () => {
  // Five competing sowing dates for one field is noise; the farmer has not
  // decided yet.
  const many = advisory({
    recommendations: Array.from({ length: 5 }, (_, i) => ({
      crop_code: `C${i}`,
      name: `Crop ${i}`,
      calendar: {
        sowing_window: { start: '2026-10-20', end: '2026-11-25' },
        harvest_window: { start: '2027-03-01', end: '2027-03-20' },
      },
    })),
  });
  assert.equal(reminderEvents(many, LABELS, name).length, 2);
});

test('a crop with no calendar produces no events rather than a bad one', () => {
  const undated = advisory({
    recommendations: [{ crop_code: 'X', name: 'X', calendar: null }],
  });
  assert.deepEqual(reminderEvents(undated, LABELS, name), []);
});

test('crop names are translated, not hardcoded', () => {
  const events = reminderEvents(advisory(), LABELS, () => 'मसूर');
  assert.ok(events[0].summary.includes('मसूर'));
});

test('DTEND is the day after DTSTART', () => {
  // All-day events have an exclusive end. Same-day start and end imports as a
  // zero-length event, which several calendars drop entirely.
  const ics = buildIcs(reminderEvents(advisory(), LABELS, name));
  assert.match(ics, /DTSTART;VALUE=DATE:20261020/);
  assert.match(ics, /DTEND;VALUE=DATE:20261021/);
});

test('month rollover in DTEND is handled', () => {
  const endOfMonth = advisory({
    recommendations: [
      {
        crop_code: 'X',
        name: 'X',
        calendar: {
          sowing_window: { start: '2026-10-31', end: '2026-11-25' },
          harvest_window: { start: '2026-12-31', end: '2027-01-10' },
        },
      },
    ],
  });
  const ics = buildIcs(reminderEvents(endOfMonth, LABELS, name));
  assert.match(ics, /DTEND;VALUE=DATE:20261101/);
  // And across the year boundary.
  assert.match(ics, /DTEND;VALUE=DATE:20270101/);
});

test('lines are CRLF terminated', () => {
  // Bare newlines are a silent-drop cause in several importers.
  const ics = buildIcs(reminderEvents(advisory(), LABELS, name));
  const bareNewlines = ics.split('\n').filter((line) => !line.endsWith('\r'));
  // Only the trailing empty string after the final CRLF may lack one.
  assert.deepEqual(bareNewlines, ['']);
});

test('long lines are folded below the 75-octet limit', () => {
  const wordy = {
    ...LABELS,
    description: () =>
      'A description well beyond seventy five characters, which RFC 5545 says must be folded onto continuation lines rather than sent as one long line.',
  };
  const ics = buildIcs(reminderEvents(advisory(), wordy, name));
  for (const line of ics.split('\r\n')) {
    assert.ok(line.length <= 75, `line too long (${line.length}): ${line.slice(0, 40)}…`);
  }
});

test('separators in text are escaped', () => {
  // An unescaped comma or semicolon ends the property early and corrupts the
  // rest of the event.
  const risky = { ...LABELS, sow: () => 'Sow wheat, barley; now' };
  const ics = buildIcs(reminderEvents(advisory(), risky, name));
  assert.match(ics, /SUMMARY:Sow wheat\\, barley\\; now/);
});

test('the calendar is structurally complete', () => {
  const ics = buildIcs(reminderEvents(advisory(), LABELS, name));
  assert.equal((ics.match(/BEGIN:VEVENT/g) ?? []).length, 2);
  assert.equal((ics.match(/END:VEVENT/g) ?? []).length, 2);
  assert.match(ics, /^BEGIN:VCALENDAR/);
  assert.match(ics, /END:VCALENDAR\r\n$/);
});

test('every event carries an alarm ahead of the date', () => {
  // Land has to be prepared before sowing day; a reminder that arrives that
  // morning is already late.
  const ics = buildIcs(reminderEvents(advisory(), LABELS, name));
  assert.equal((ics.match(/BEGIN:VALARM/g) ?? []).length, 2);
  assert.match(ics, /TRIGGER:-P7D/);
});

test('UIDs are unique per event', () => {
  // Duplicate UIDs make a calendar overwrite one event with the other.
  const events = reminderEvents(advisory(), LABELS, name);
  assert.equal(new Set(events.map((e) => e.uid)).size, events.length);
});
