'use client';

import { BarChart3, Info } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useTranslation } from '@/i18n/provider';
import type { Productivity } from '@/types/api';

/**
 * This plot's growing vigour against the farmland around it.
 *
 * WHY A BAR RATHER THAN A NUMBER
 * ------------------------------
 * "62nd percentile" is precise and means nothing to most readers. The bar
 * shows the neighbourhood's spread with the plot marked on it, which answers
 * the actual question — am I doing better or worse than the fields around me,
 * and by how much — without asking anyone to interpret a statistic.
 *
 * WHAT THE PANEL REFUSES TO CLAIM
 * -------------------------------
 * That this is yield, and that it is a judgement of the farmer. Amplitude
 * measures biomass; a lush crop that lodges before harvest scores well here
 * and yields badly. And the neighbours may be growing something else — a pulse
 * cannot match a paddy for canopy however well it is grown.
 *
 * Both caveats sit next to the result rather than under it. A farmer told they
 * are "below average" will read that as a verdict on their farming unless the
 * page says otherwise in the same breath.
 */

const BAND_STYLE: Record<string, string> = {
  well_above: 'border-emerald-300 text-emerald-800',
  above: 'border-emerald-300 text-emerald-800',
  typical: 'border-border text-muted-foreground',
  below: 'border-amber-300 text-amber-900',
  well_below: 'border-amber-300 text-amber-900',
  unknown: 'border-border text-muted-foreground',
};

export function ProductivityPanel({
  productivity,
}: {
  productivity: Productivity | null | undefined;
}) {
  const t = useTranslation();
  if (!productivity) return null;

  const { band, percentile, plot_amplitude: amplitude, percentiles } = productivity;
  const known = band !== 'unknown' && percentile !== null;

  // The bar spans p10 to p90 of the neighbourhood. Values outside that are
  // clamped to the ends, which matches how the percentile itself is capped:
  // we know the plot is beyond the range, not where beyond it.
  const low = percentiles['10'];
  const high = percentiles['90'];
  const position =
    known && amplitude !== null && low !== undefined && high !== undefined && high > low
      ? Math.min(100, Math.max(0, ((amplitude - low) / (high - low)) * 100))
      : null;

  return (
    <Card data-print-card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <BarChart3 className="h-4 w-4 text-muted-foreground" aria-hidden />
          {t('productivity.title')}
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          {t('productivity.help', { km: productivity.neighbourhood_km })}
        </p>
      </CardHeader>

      <CardContent>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-lg font-semibold">{t(`productivity.band.${band}`)}</span>
          <Badge variant="outline" className={BAND_STYLE[band] ?? BAND_STYLE.unknown}>
            {known
              ? t('productivity.percentile', { percentile })
              : t('productivity.noComparison')}
          </Badge>
        </div>

        {position !== null && (
          <div className="mt-4">
            <div className="relative h-3 w-full rounded-full bg-gradient-to-r from-amber-100 via-muted to-emerald-100">
              {/* The marker is a line, not a dot: a dot invites reading a
                  precision this measure does not have. */}
              <div
                className="absolute top-[-4px] h-5 w-0.5 bg-foreground"
                style={{ left: `calc(${position}% - 1px)` }}
                aria-hidden
              />
            </div>
            <div className="mt-1 flex justify-between text-xs text-muted-foreground">
              <span>{t('productivity.lowEnd')}</span>
              <span>{t('productivity.middle')}</span>
              <span>{t('productivity.highEnd')}</span>
            </div>
          </div>
        )}

        {amplitude !== null && (
          <p className="mt-3 text-sm text-muted-foreground">
            {t('productivity.amplitude', { value: amplitude.toFixed(2) })}
          </p>
        )}

        {/* Beside the result, not beneath it. "Below average" reads as a
            judgement on the farmer unless it is qualified in the same breath. */}
        <p className="mt-3 flex items-start gap-2 rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          {t('productivity.notYield')}
        </p>

        {productivity.caveat_codes.length > 0 && (
          <ul className="mt-2 space-y-1">
            {productivity.caveat_codes
              .filter((code) => code !== 'not_a_yield_measure')
              .map((code) => (
                <li key={code} className="text-xs text-muted-foreground">
                  {t(`productivity.caveat.${code}`)}
                </li>
              ))}
          </ul>
        )}

        {productivity.sample_pixels > 0 && (
          <p className="mt-2 text-xs text-muted-foreground">
            {t('productivity.sample', {
              pixels: productivity.sample_pixels.toLocaleString('en-IN'),
              km: productivity.neighbourhood_km,
            })}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
