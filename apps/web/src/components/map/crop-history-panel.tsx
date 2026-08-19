'use client';

import { History, Info } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useTranslation } from '@/i18n/provider';
import type { CropHistory, Level } from '@/types/api';

/**
 * Cropping intensity and season timing, read off the NDVI series.
 *
 * WHAT THE PANEL REFUSES TO SAY
 * -----------------------------
 * Which crop it was. The note about that is not a disclaimer bolted on at the
 * bottom — it is the second thing on the card, because "satellite crop history"
 * invites exactly that reading and a farmer who assumes we identified their
 * wheat will trust the next wrong thing too.
 *
 * THE ERROR RUNS ONE WAY
 * ----------------------
 * Optical imagery misses crops under monsoon cloud, so a double-cropped field
 * can read as single-cropped. It can never read the other way round. When
 * kharif coverage is poor the panel says so in those terms — "may be cropped
 * more often than shown, never less" — rather than offering a vague accuracy
 * hedge that leaves the direction of the error to the reader's imagination.
 */

const CONFIDENCE_STYLE: Record<Level, string> = {
  high: 'border-emerald-300 text-emerald-800',
  medium: 'border-amber-300 text-amber-900',
  low: 'border-red-300 text-red-800',
};

function monthLabel(yyyymm: string, locale: string): string {
  const [year, month] = yyyymm.split('-').map(Number);
  if (!year || !month) return yyyymm;
  // Every locale this app speaks is an Indian variant, so the tag is simply
  // `<code>-IN`. The previous version tested only for Hindi and sent everyone
  // else to en-IN, which put "Nov 2026" in Latin script in the middle of a
  // Tamil sentence.
  return new Date(year, month - 1, 1).toLocaleDateString(`${locale}-IN`, {
    month: 'short',
    year: 'numeric',
  });
}

export function CropHistoryPanel({
  history,
  locale = 'en',
}: {
  history: CropHistory | null | undefined;
  locale?: string;
}) {
  const t = useTranslation();
  if (!history) return null;

  const seasons = history.seasons_used.map((s) => t(`season.${s}`)).join(', ');

  return (
    <Card data-print-card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <History className="h-4 w-4 text-muted-foreground" aria-hidden />
          {t('history.title')}
        </CardTitle>
        <p className="text-sm text-muted-foreground">{t('history.help')}</p>
      </CardHeader>

      <CardContent>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-lg font-semibold">
            {t(`history.intensity.${history.intensity}`)}
          </span>
          <Badge variant="outline" className={CONFIDENCE_STYLE[history.confidence]}>
            {t(`crop.${history.confidence}`)}
          </Badge>
        </div>

        <p className="mt-1 text-sm text-muted-foreground">
          {t(`history.intensityNote.${history.intensity}`, { seasons })}
        </p>

        {/* Second, not last: the panel's name invites a claim it does not make. */}
        <p className="mt-3 flex items-start gap-2 rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          {t('history.notCropId')}
        </p>

        {history.cycles.length > 0 && (
          <div className="mt-4">
            <h3 className="text-sm font-semibold">{t('history.cycles')}</h3>
            <ul className="mt-2 space-y-1.5">
              {history.cycles.map((cycle) => (
                <li
                  key={`${cycle.start_month}-${cycle.peak_month}`}
                  className="flex flex-wrap items-baseline justify-between gap-2 text-sm"
                >
                  <span className="flex items-center gap-2">
                    <Badge variant="outline">{t(`season.${cycle.season}`)}</Badge>
                    <span className="text-muted-foreground">
                      {monthLabel(cycle.start_month, locale)} –{' '}
                      {monthLabel(cycle.end_month, locale)}
                    </span>
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {t('history.peak', { month: monthLabel(cycle.peak_month, locale) })} ·{' '}
                    {cycle.peak_ndvi.toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <p className="mt-4 text-xs text-muted-foreground">
          {t('history.observed', {
            observed: history.observed_months,
            total: history.total_months,
          })}
        </p>

        {history.caveat_codes.length > 0 && (
          <ul className="mt-2 space-y-1">
            {history.caveat_codes.map((code) => (
              <li key={code} className="text-xs text-muted-foreground">
                {t(`history.caveat.${code}`)}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
