/**
 * What the "listen" button actually says.
 *
 * WHY THIS IS A SEPARATE, PURE MODULE
 * -----------------------------------
 * A spoken advisory is a second rendering of the same result, and two
 * renderings of one result are exactly where this codebase keeps finding bugs:
 * the page says one thing, the other surface says another, and nobody notices
 * because you cannot see both at once. Here you literally cannot — the screen
 * is visual and the voice is not.
 *
 * So the script is built as data, in a file with no React in it, and tested.
 *
 * WHAT IS DELIBERATELY SPOKEN
 * ---------------------------
 * The warnings. A farmer who listens instead of reading is usually the farmer
 * who cannot comfortably read, and the amber box at the top of the page is the
 * one thing on it that changes what they should do. Speaking the ranking and
 * skipping the cautions would be worse than speaking nothing.
 *
 * WHAT IS DELIBERATELY NOT SPOKEN
 * -------------------------------
 * Everything below the top three: reasons, factor scores, water budgets,
 * rotation notes. Not because they do not matter, but because a two-minute
 * monologue is not listened to. The voice is a summary that points back at the
 * page; it is never the only copy of anything.
 *
 * MONEY AND ITS HEDGE ARE ONE SENTENCE
 * ------------------------------------
 * `voice.money` contains both the figure and "this is an estimate". They are
 * not two parts, because two parts can be reordered, or the second one dropped
 * by an edit six months from now, and the result would be a synthetic voice
 * promising a farmer a number. One string cannot come apart.
 *
 * NUMBERS ARE PLAIN, NOT FORMATTED CURRENCY
 * -----------------------------------------
 * `formatMoney` produces "₹45,000". Speech synthesisers do not reliably read
 * the rupee sign — some say nothing, some say "R". The word "rupees" lives in
 * the translated sentence instead, where a Hindi voice reads "रुपये" properly.
 */

export interface SpokenPart {
  /** i18n key, resolved by the caller against its own dictionary. */
  key: string;
  params?: Record<string, string | number>;
  /**
   * Params whose VALUES are themselves i18n keys, resolved before substitution.
   *
   * Confidence arrives from the server as the bare word "high". Dropping that
   * into a Hindi sentence produces "उपयुक्तता high" — an English word in the
   * middle of a Hindi utterance, which a Hindi voice mispronounces and a Hindi
   * speaker may not recognise at all. Nothing about the visible page reveals
   * this, because the badge on screen has always been translated separately.
   */
  paramKeys?: Record<string, string>;
}

/** Only the fields the script reads. Anything wider would be a lie. */
export interface AdvisoryInput {
  location_resolved: { district_name: string; area_ha: number };
  recommendations: Array<{
    rank: number;
    crop_code: string;
    name: string;
    confidence: string;
    economics: { net_margin: number | null };
  }>;
  warnings: Array<{ code: string }>;
  request_echo?: { season?: string | null } | null;
}

/** Three is about twenty seconds of speech. Five is not listened to. */
const SPOKEN_RANKS = 3;

/** Rupees. Paise in a spoken estimate would be false precision. */
const spokenMoney = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });

/**
 * Hectares, which are usually fractional.
 *
 * These cannot share a formatter. Most plots in this country are under a
 * hectare, so rounding to whole numbers would tell a farmer with 0.81 ha that
 * the figure is "for your 1 hectare plot" — and since the money beside it was
 * computed on 0.81, the two halves of one sentence would disagree.
 */
const spokenArea = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });

/**
 * Build the script.
 *
 * `cropName` is injected rather than imported so this stays pure — the real one
 * is a React hook that reads the crops endpoint and the active locale.
 */
export function advisoryScript(
  data: AdvisoryInput,
  cropName: (code: string, fallback: string) => string,
): SpokenPart[] {
  const parts: SpokenPart[] = [];
  const top = data.recommendations.slice(0, SPOKEN_RANKS);

  parts.push({
    key: 'voice.place',
    params: { district: data.location_resolved.district_name },
  });

  if (top.length === 0) {
    // Say so out loud. Silence after pressing a button reads as a broken
    // button, and the farmer waits for a result that is never coming.
    parts.push({ key: 'voice.empty' });
  }

  for (const item of top) {
    parts.push({
      key: 'voice.crop',
      params: { rank: item.rank, crop: cropName(item.crop_code, item.name) },
      // Reuses the badge's own dictionary entries, so the spoken word and the
      // word on screen can never drift apart.
      paramKeys: { confidence: `crop.${item.confidence}` },
    });
  }

  const best = top[0];
  if (best && best.economics.net_margin !== null) {
    parts.push({
      key: 'voice.money',
      params: {
        crop: cropName(best.crop_code, best.name),
        amount: spokenMoney.format(Math.round(best.economics.net_margin)),
        area: spokenArea.format(data.location_resolved.area_ha),
      },
    });
  }

  if (data.warnings.length > 0) {
    // Last, because it is the instruction the farmer should be left holding.
    parts.push({
      key: data.warnings.length === 1 ? 'voice.warningsOne' : 'voice.warnings',
      params: { count: data.warnings.length },
    });
  }

  return parts;
}

/** Join rendered parts into one utterance. */
export function joinScript(rendered: string[]): string {
  return rendered.join(' ');
}

/**
 * Resolve one part against a dictionary.
 *
 * Kept here rather than inline in the component so the `paramKeys` step cannot
 * be forgotten by a second caller — forgetting it produces an English word in
 * a Hindi sentence, which nothing on screen would reveal.
 */
export function renderPart(
  part: SpokenPart,
  t: (key: string, params?: Record<string, string | number>) => string,
): string {
  const resolved: Record<string, string | number> = { ...part.params };
  for (const [name, key] of Object.entries(part.paramKeys ?? {})) {
    resolved[name] = t(key);
  }
  return t(part.key, resolved);
}
