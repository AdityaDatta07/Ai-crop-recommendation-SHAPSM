/**
 * Sowing and harvest reminders, as a calendar file.
 *
 * WHY .ics AND NOT SMS OR WHATSAPP
 * --------------------------------
 * Sending a message needs a telephony provider, a registered sender, a
 * template approval and a per-message cost — the same wall that got IVR cut
 * from the voice feature. None of that exists here, and building half of it
 * would produce a reminder system that silently never fires.
 *
 * A calendar file needs none of it. The farmer's own phone does the reminding,
 * offline, for free, and keeps working if this app disappears entirely. It is
 * the smaller promise, and it is one we can actually keep.
 *
 * WHY THE DATES ARE NOT INVENTED
 * ------------------------------
 * Every date here comes from the advisory's own calendar — the same sowing and
 * harvest windows shown on the page. Nothing is offset, padded or "helpfully"
 * adjusted, so a reminder can never disagree with the screen it came from.
 */

import type { RecommendationResponse } from '@/types/api';

/** RFC 5545 wants YYYYMMDD for all-day events. */
function asDate(iso: string): string {
  return iso.replaceAll('-', '');
}

/** The day after, because DTEND on an all-day event is exclusive. */
function dayAfter(iso: string): string {
  const date = new Date(`${iso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + 1);
  return asDate(date.toISOString().slice(0, 10));
}

/**
 * Line folding, which is not optional.
 *
 * RFC 5545 caps lines at 75 octets. Google Calendar and Apple both tolerate
 * longer ones; some Android importers silently drop the whole event instead,
 * which would look exactly like the feature not working.
 */
function fold(line: string): string {
  if (line.length <= 73) return line;
  const parts: string[] = [line.slice(0, 73)];
  let rest = line.slice(73);
  while (rest.length > 72) {
    parts.push(` ${rest.slice(0, 72)}`);
    rest = rest.slice(72);
  }
  parts.push(` ${rest}`);
  return parts.join('\r\n');
}

function escape(text: string): string {
  return text.replace(/[\\;,]/g, (match) => `\\${match}`).replace(/\n/g, '\\n');
}

export interface ReminderEvent {
  uid: string;
  date: string;
  summary: string;
  description: string;
}

/**
 * Build the events for one advisory.
 *
 * `labels` is injected so this file holds no English: the caller passes
 * already-translated strings, and a Hindi user gets a Hindi calendar entry.
 */
export function reminderEvents(
  data: RecommendationResponse,
  labels: {
    sow: (crop: string) => string;
    harvest: (crop: string) => string;
    description: (crop: string, district: string) => string;
  },
  cropName: (code: string, fallback: string) => string,
  limit = 1,
): ReminderEvent[] {
  const events: ReminderEvent[] = [];
  const district = data.location_resolved.district_name;

  // Only the top crop by default. A calendar with five competing sowing dates
  // for one field is noise, and the farmer has not decided yet.
  for (const item of data.recommendations.slice(0, limit)) {
    const name = cropName(item.crop_code, item.name);
    const sowing = item.calendar?.sowing_window?.start;
    const harvest = item.calendar?.harvest_window?.start;

    if (sowing) {
      events.push({
        uid: `${data.request_id}-${item.crop_code}-sow`,
        date: sowing,
        summary: labels.sow(name),
        description: labels.description(name, district),
      });
    }
    if (harvest) {
      events.push({
        uid: `${data.request_id}-${item.crop_code}-harvest`,
        date: harvest,
        summary: labels.harvest(name),
        description: labels.description(name, district),
      });
    }
  }
  return events;
}

export function buildIcs(events: ReminderEvent[]): string {
  const stamp = `${new Date().toISOString().replace(/[-:]/g, '').split('.')[0]}Z`;

  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Beej Nirnay//Advisory reminders//EN',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
  ];

  for (const event of events) {
    lines.push(
      'BEGIN:VEVENT',
      `UID:${event.uid}@beej-nirnay`,
      `DTSTAMP:${stamp}`,
      `DTSTART;VALUE=DATE:${asDate(event.date)}`,
      `DTEND;VALUE=DATE:${dayAfter(event.date)}`,
      fold(`SUMMARY:${escape(event.summary)}`),
      fold(`DESCRIPTION:${escape(event.description)}`),
      // A week ahead. Land has to be prepared before sowing day, so a reminder
      // that arrives on the morning itself is already late.
      'BEGIN:VALARM',
      'TRIGGER:-P7D',
      'ACTION:DISPLAY',
      fold(`DESCRIPTION:${escape(event.summary)}`),
      'END:VALARM',
      'END:VEVENT',
    );
  }

  lines.push('END:VCALENDAR');
  // CRLF, per the spec. Bare newlines are another silent-drop cause.
  return `${lines.join('\r\n')}\r\n`;
}

export function downloadIcs(filename: string, ics: string): void {
  const blob = new Blob([ics], { type: 'text/calendar;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
