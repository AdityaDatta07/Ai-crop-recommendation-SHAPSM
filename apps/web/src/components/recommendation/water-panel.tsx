'use client';

import { CloudRain, Droplets, TriangleAlert } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatNumber, NOT_AVAILABLE } from '@/lib/format';
import { useI18n } from '@/i18n/provider';
import { useCropName } from '@/i18n/use-crop-name';
import type { Irrigation, WaterBudget } from '@/types/api';

/**
 * What each crop needs, what the rain gives, and the gap.
 *
 * TWO NUMBERS THAT LOOK LIKE THEY DISAGREE, AND DO NOT
 * -----------------------------------------------------
 * The suitability reasons above compare the crop against TOTAL rainfall. This
 * panel compares it against USABLE rainfall, which is lower — some runs off,
 * some drains past the roots. So the same field can read "859 mm meets the
 * 600 mm need" up there and "13 mm short" down here. The note under the
 * rainfall figure explains that, because otherwise it reads as a bug.
 *
 * WHAT IS FIELD-WIDE AND WHAT IS NOT
 * ----------------------------------
 * Only the rain that falls belongs to the field. How much of it a crop can USE
 * depends on how many months that crop occupies, so it is a per-crop number
 * and lives in the table. Printing one crop's figure above the table read as a
 * fact about the field: maize sees 537 mm of the same 859 mm that wheat sees
 * 597 mm of.
 *
 * AND ONE CAVEAT THAT MATTERS MORE THAN THE ARITHMETIC
 * ----------------------------------------------------
 * The rainfall is a thirty-year normal. It is not a forecast, and a budget
 * that only just balances on the average is tight, not safe. That warning sits
 * at the top of the panel rather than in a footnote.
 */

const STATUS_ICON = {
  rain_sufficient: CloudRain,
  surplus: CloudRain,
  needs_irrigation: Droplets,
  cannot_meet: TriangleAlert,
  unknown: Droplets,
} as const;

export function WaterPanel({
  budgets,
  irrigation,
}: {
  budgets: WaterBudget[] | undefined;
  irrigation?: Irrigation | null;
}) {
  const { t } = useI18n();
  const cropName = useCropName();

  if (!budgets || budgets.length === 0) return null;

  const top = budgets[0];
  const Icon = STATUS_ICON[top.status] ?? Droplets;
  const source = t(`season.${irrigation ?? 'rainfed'}`);

  return (
    <Card data-print-card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Droplets className="h-4 w-4 text-muted-foreground" aria-hidden />
          {t('water.title')}
        </CardTitle>
        <p className="text-sm text-muted-foreground">{t('water.help')}</p>
      </CardHeader>

      <CardContent>
        {/* The caveat leads, because a normal read as a forecast is the way
            this panel does harm. */}
        <p
          data-print-warning
          className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
        >
          {t('water.notAForecast')}
        </p>

        {/* Only the rainfall itself is field-wide. How much of it a crop can
            use depends on how long that crop is in the ground, so "usable" is
            a per-crop figure and belongs in the table, not up here presented
            as a fact about the field. Maize sees 537 mm of the same 859 that
            wheat sees 597 mm of. */}
        {top.season_rainfall_mm !== null && (
          <div className="mt-4 rounded-md border border-border p-3">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <span className="text-sm font-medium">{t('water.falls')}</span>
              <span className="font-mono text-sm font-semibold">
                {formatNumber(top.season_rainfall_mm, 'mm')}
              </span>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{t('water.usableNote')}</p>
          </div>
        )}

        {/* ------------------------------------------------------ per crop */}
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="py-1.5 pr-3 font-medium">{t('water.crop')}</th>
                <th className="py-1.5 pr-3 text-right font-medium">{t('water.needsLabel')}</th>
                <th className="py-1.5 pr-3 text-right font-medium">{t('water.usable')}</th>
                <th className="py-1.5 pr-3 text-right font-medium">{t('water.gap')}</th>
                <th className="py-1.5 pr-3 text-right font-medium">{t('water.waterings')}</th>
                <th className="py-1.5 text-right font-medium">{t('water.volume')}</th>
              </tr>
            </thead>
            <tbody>
              {budgets.map((budget) => (
                <tr key={budget.crop_code} className="border-b border-border/60 last:border-0">
                  <td className="py-2 pr-3">
                    <span className="font-medium">
                      {cropName(budget.crop_code, budget.name)}
                    </span>
                    {/* Colour alone must not carry "you cannot do this". */}
                    {budget.status === 'cannot_meet' && (
                      <Badge variant="outline" className="ml-2 border-red-300 text-red-800">
                        {t('water.gap')}
                      </Badge>
                    )}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-xs">
                    {budget.requirement_mm}–{budget.comfortable_mm} mm
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-xs">
                    {budget.effective_rainfall_mm === null ||
                    budget.effective_rainfall_mm === undefined
                      ? NOT_AVAILABLE
                      : formatNumber(budget.effective_rainfall_mm, 'mm')}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-xs">
                    {budget.deficit_mm === null || budget.deficit_mm === undefined
                      ? NOT_AVAILABLE
                      : budget.deficit_mm === 0
                        ? t('water.noneNeeded')
                        : formatNumber(budget.deficit_mm, 'mm')}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-xs">
                    {budget.waterings === null || budget.waterings === undefined
                      ? NOT_AVAILABLE
                      : budget.waterings === 0
                        ? t('water.noneNeeded')
                        : t('water.aboutN', { count: budget.waterings })}
                  </td>
                  <td className="py-2 text-right font-mono text-xs">
                    {budget.deficit_m3 === null || budget.deficit_m3 === undefined
                      ? NOT_AVAILABLE
                      : budget.deficit_m3 === 0
                        ? '—'
                        : formatNumber(budget.deficit_m3, 'm³')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Which end of the range the gap closes to. The table shows
            "400-650 mm" beside a gap, which reads as though closing the gap
            lands the crop inside the band. It lands it on 400 — the bottom
            edge. Saying so costs one line and prevents a farmer under-watering
            while believing they have followed the advice. */}
        {top.deficit_mm !== null &&
          top.deficit_mm > 0 &&
          top.waterings_comfortable !== null &&
          top.waterings_comfortable > (top.waterings ?? 0) && (
            <p className="mt-3 text-xs text-muted-foreground">
              {t('water.targetsMinimum', {
                crop: cropName(top.crop_code, top.name),
                comfortable: top.comfortable_mm,
                waterings: top.waterings_comfortable,
              })}
            </p>
          )}

        {/* What it means for the crop actually being recommended. */}
        <p className="mt-4 flex items-start gap-2 rounded-md border border-border bg-muted/40 p-3 text-sm">
          <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          <span>{t(`water.status.${top.status}`, { source })}</span>
        </p>

        <p className="mt-3 text-xs text-muted-foreground">
          {t('water.perWatering', { depth: 60 })} {t('water.method')}
        </p>
      </CardContent>
    </Card>
  );
}
