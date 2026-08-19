'use client';

import { Sprout, Coins, Check } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatMoney, NOT_AVAILABLE } from '@/lib/format';
import { useI18n } from '@/i18n/provider';
import { useCropName } from '@/i18n/use-crop-name';
import type { Recommendation } from '@/types/api';

/**
 * The same five crops, ordered two ways.
 *
 * THE QUESTION THIS ANSWERS
 * -------------------------
 * "If wheat earns 67% more, why is chickpea first?"
 *
 * Because the ranking answers what suits the field, and money is 9% of that
 * score. Both are legitimate questions and the app was only showing one, so a
 * farmer looking at a lower-ranked, better-paying crop reasonably concluded the
 * ranking was broken. It was not — it was answering something else.
 *
 * Showing both orderings is more honest than picking one. It also declines to
 * resolve the trade-off on the farmer's behalf, which is right: how much income
 * a rotation break is worth depends on their soil, their debts and their year,
 * none of which this app knows.
 *
 * CROPS WITH NO PRICE
 * -------------------
 * They appear in the fit column and are absent from the return column, marked
 * as unpriceable rather than dropped. Silently omitting them would make the
 * return list look complete when it is not.
 */
export function TwoOrderings({ recommendations }: { recommendations: Recommendation[] }) {
  const { t } = useI18n();
  const cropName = useCropName();

  if (recommendations.length < 2) return null;

  const byFit = [...recommendations].sort((a, b) => a.rank - b.rank);
  const byReturn = recommendations
    .filter((item) => item.rank_by_return != null)
    .sort((a, b) => (a.rank_by_return ?? 0) - (b.rank_by_return ?? 0));

  const unpriced = recommendations.filter((item) => item.rank_by_return == null);

  // A crop near the top of BOTH lists needs no trade-off reasoning at all.
  const topOf = (list: Recommendation[]) =>
    new Set(list.slice(0, 3).map((item) => item.crop_code));
  const agreed = new Set(
    [...topOf(byFit)].filter((code) => topOf(byReturn).has(code)),
  );

  const bestFit = byFit[0];
  const bestReturn = byReturn[0];
  const sameWinner = bestFit && bestReturn && bestFit.crop_code === bestReturn.crop_code;

  return (
    <Card data-print-card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{t('orderings.title')}</CardTitle>
        <p className="text-sm text-muted-foreground">{t('orderings.help')}</p>
      </CardHeader>

      <CardContent>
        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <Sprout className="h-4 w-4 text-muted-foreground" aria-hidden />
              {t('orderings.byFit')}
            </h3>
            <p className="mt-0.5 text-xs text-muted-foreground">{t('orderings.byFitHelp')}</p>
            <ol className="mt-2 space-y-1.5">
              {byFit.map((item) => (
                <li
                  key={item.crop_code}
                  className="flex items-baseline justify-between gap-2 text-sm"
                >
                  <span className="flex items-center gap-1.5">
                    <span className="w-4 shrink-0 font-mono text-xs text-muted-foreground">
                      {item.rank}
                    </span>
                    {cropName(item.crop_code, item.name)}
                    {agreed.has(item.crop_code) && (
                      <Check className="h-3.5 w-3.5 shrink-0 text-emerald-700" aria-hidden />
                    )}
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {item.score.toFixed(2)}
                  </span>
                </li>
              ))}
            </ol>
          </div>

          <div>
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <Coins className="h-4 w-4 text-muted-foreground" aria-hidden />
              {t('orderings.byReturn')}
            </h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {t('orderings.byReturnHelp')}
            </p>
            <ol className="mt-2 space-y-1.5">
              {byReturn.map((item) => (
                <li
                  key={item.crop_code}
                  className="flex items-baseline justify-between gap-2 text-sm"
                >
                  <span className="flex items-center gap-1.5">
                    <span className="w-4 shrink-0 font-mono text-xs text-muted-foreground">
                      {item.rank_by_return}
                    </span>
                    {cropName(item.crop_code, item.name)}
                    {agreed.has(item.crop_code) && (
                      <Check className="h-3.5 w-3.5 shrink-0 text-emerald-700" aria-hidden />
                    )}
                  </span>
                  <span className="font-mono text-xs">
                    {item.economics.net_margin === null
                      ? NOT_AVAILABLE
                      : formatMoney(item.economics.net_margin)}
                  </span>
                </li>
              ))}
            </ol>

            {/* Named, not quietly dropped: a return list missing crops would
                look complete while being partial. */}
            {unpriced.length > 0 && (
              <p className="mt-2 text-xs text-muted-foreground">
                {t('orderings.unpriced', {
                  crops: unpriced
                    .map((item) => cropName(item.crop_code, item.name))
                    .join(', '),
                })}
              </p>
            )}
          </div>
        </div>

        <div className="mt-4 rounded-md border border-border bg-muted/40 p-3 text-sm">
          {sameWinner ? (
            <span>
              {t('orderings.agree', { crop: cropName(bestFit.crop_code, bestFit.name) })}
            </span>
          ) : (
            <span>
              {t('orderings.disagree', {
                fit: cropName(bestFit.crop_code, bestFit.name),
                money: cropName(bestReturn.crop_code, bestReturn.name),
              })}
            </span>
          )}
        </div>

        {agreed.size > 0 && (
          <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Badge variant="outline" className="border-emerald-300 text-emerald-800">
              <Check className="mr-1 h-3 w-3" aria-hidden />
              {t('orderings.inBoth')}
            </Badge>
            {t('orderings.inBothHelp')}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
