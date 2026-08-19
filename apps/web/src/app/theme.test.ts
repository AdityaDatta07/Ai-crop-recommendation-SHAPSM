/**
 * Contrast guards for the dark canvas.
 *
 * WHY THIS EXISTS
 * ---------------
 * The redesign inverted the page: the field is deep green and the cards are
 * white. That is a better answer for reading outdoors on a cheap phone, but it
 * introduces a failure mode the old light theme did not have — any text placed
 * on the canvas rather than inside a card is near-white on near-black, and
 * getting it wrong produces text that is invisible rather than merely ugly.
 *
 * Three of those slipped through on the first pass: the "Ranked recommendations"
 * heading, the empty-results message, and the whole offline page were still
 * using `text-muted-foreground`, a mid grey chosen for white backgrounds.
 *
 * Colours are read out of globals.css rather than duplicated here, so this
 * cannot drift into testing a copy of the theme instead of the theme.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'globals.css'), 'utf-8');

/** Pull `140 45% 96%` out of the stylesheet for a given declaration. */
function hsl(pattern: RegExp): [number, number, number] {
  const match = css.match(pattern);
  assert.ok(match, `could not find ${pattern} in globals.css — this guard is blind`);
  const [h, s, l] = match!.slice(1, 4).map(Number);
  return [h, s, l];
}

function toRgb([h, s, l]: [number, number, number]): [number, number, number] {
  const sat = s / 100;
  const light = l / 100;
  const c = (1 - Math.abs(2 * light - 1)) * sat;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = light - c / 2;
  const table: [number, number, number][] = [
    [c, x, 0], [x, c, 0], [0, c, x], [0, x, c], [x, 0, c], [c, 0, x],
  ];
  const [r, g, b] = table[Math.floor(h / 60) % 6];
  return [r + m, g + m, b + m];
}

function luminance(rgb: [number, number, number]): number {
  const [r, g, b] = rgb.map((channel) =>
    channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: [number, number, number], b: [number, number, number]): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// Read the actual theme values.
const CANVAS = toRgb(hsl(/background-color:\s*hsl\((\d+)\s+(\d+)%\s+(\d+)%\)/));
const CANVAS_DARK = toRgb(hsl(/linear-gradient\(hsl\([\d\s%]+\),\s*hsl\((\d+)\s+(\d+)%\s+(\d+)%\)\)/));
const ON_CANVAS = toRgb(hsl(/\.on-canvas\s*\{\s*color:\s*hsl\((\d+)\s+(\d+)%\s+(\d+)%\)/));
const ON_CANVAS_MUTED = toRgb(hsl(/\.on-canvas-muted\s*\{\s*color:\s*hsl\((\d+)\s+(\d+)%\s+(\d+)%\)/));
const FOREGROUND = toRgb(hsl(/--foreground:\s*(\d+)\s+(\d+)%\s+(\d+)%/));
const WHITE: [number, number, number] = [1, 1, 1];

/** WCAG AA for body text. */
const AA = 4.5;

test('body text on a white card is comfortably legible', () => {
  assert.ok(contrast(FOREGROUND, WHITE) >= AA, `${contrast(FOREGROUND, WHITE).toFixed(2)}:1`);
});

test('canvas text passes against the lightest part of the gradient', () => {
  // The gradient is not one colour. Checking only the darkest end would pass a
  // theme that is unreadable at the top of the page, where the heading is.
  const ratio = contrast(ON_CANVAS, CANVAS);
  assert.ok(ratio >= AA, `on-canvas is ${ratio.toFixed(2)}:1 against the canvas`);
});

test('canvas text passes against the darkest part of the gradient', () => {
  const ratio = contrast(ON_CANVAS, CANVAS_DARK);
  assert.ok(ratio >= AA, `on-canvas is ${ratio.toFixed(2)}:1 against the dark end`);
});

test('muted canvas text is still readable, not decorative', () => {
  // This one carries the disclaimer and the score caveat. If it fails, the
  // sentences the project most wants read are the ones that disappear.
  const ratio = contrast(ON_CANVAS_MUTED, CANVAS);
  assert.ok(ratio >= AA, `on-canvas-muted is ${ratio.toFixed(2)}:1`);
});

test('the canvas is actually dark', () => {
  // Guards the assumption every on-canvas colour is built on. If someone
  // lightens the field back towards white, near-white text on it silently
  // becomes invisible and every ratio above still passes on the old values.
  assert.ok(luminance(CANVAS) < 0.1, 'the canvas is no longer dark; on-canvas text assumes it is');
});

test('both decorative layers are removed for print', () => {
  // The photograph prints as a grey wash and the shapes as marks across the
  // figures. A farmer takes this sheet to a bank.
  const printBlock = css.slice(css.indexOf('@media print'));
  assert.match(printBlock, /body::before,\s*\n\s*body::after\s*\{\s*\n\s*display:\s*none\s*!important/);
});

test('canvas text is forced back to black for print', () => {
  // Near-white on white is a blank sheet.
  const printBlock = css.slice(css.indexOf('@media print'));
  assert.match(printBlock, /\.on-canvas,\s*\n\s*\.on-canvas-muted\s*\{\s*\n\s*color:\s*#000\s*!important/);
});
