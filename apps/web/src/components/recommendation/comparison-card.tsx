'use client';

import { ArrowRight, CheckCircle2, TrendingDown, TrendingUp } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatMoney, formatNumber, NOT_AVAILABLE } from '@/lib/format';
import { useI18n } from '@/i18n/provider';
import { useCropName } from '@/i18n/use-crop-name';
import { useServerText } from '@/i18n/use-server-text';
import type { ComparisonSide, CropComparison } from '@/types/api';

function Side({
  side,
  label,
  highlight,
}: {
  side: ComparisonSide;
  label: string;
  highlight: boolean;
}) {
  const cropName = useCropName();
  const { t } = useI18n();
  const serverText = useServerText();

  return (
    <div
      className={
        highlight
          ? 'flex-1 rounded-lg border-2 border-primary bg-primary/5 p-4'
          : 'flex-1 rounded-lg border border-border p-4'
      }
    >
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold">{cropName(side.crop_code, side.name)}</p>

      {side.rank === null ? (
        <Badge variant="outline" className="mt-2">
          {t('comparison.notSuited')}
        </Badge>
      ) : (
        <Badge variant={highlight ? 'positive' : 'neutral'} className="mt-2">
          {t('comparison.rank', { rank: side.rank })}
        </Badge>
      )}

      <dl className="mt-3 space-y-1.5 text-sm">
        <div className="flex justify-between gap-3">
          <dt className="text-muted-foreground">{t('comparison.margin')}</dt>
          <dd className={side.net_margin === null ? 'text-muted-foreground' : 'font-semibold'}>
            {side.net_margin === null ? NOT_AVAILABLE : formatMoney(side.net_margin)}
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-muted-foreground">{t('comparison.yield')}</dt>
          <dd>{formatNumber(side.expected_yield_t_ha, 't/ha')}</dd>
        </div>
      </dl>
    </div>
  );
}

/**
 * Last season's crop against this season's recommendation.
 *
 * Both sides come from the same engine on the same field with the same prices,
 * so the only thing differing is the crop. That is what makes the gap
 * meaningful — and why we ask for the crop name and nothing else rather than
 * asking the farmer to recall last year's yields and costs.
 */
export function ComparisonCard({ comparison }: { comparison: CropComparison }) {
  const { t } = useI18n();
  const cropName = useCropName();
  const serverText = useServerText();
  const difference = comparison.margin_difference;

  const Icon =
    comparison.same_crop || difference === 0
      ? CheckCircle2
      : difference != null && difference > 0
        ? TrendingUp
        : TrendingDown;

  return (
    <Card data-print-card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{t('comparison.title')}</CardTitle>
      </CardHeader>

      <CardContent>
        <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
          <Side
            side={comparison.previous}
            label={t('comparison.lastSeason')}
            highlight={false}
          />

          <ArrowRight
            className="mx-auto hidden h-5 w-5 shrink-0 text-muted-foreground sm:block"
            aria-hidden
          />

          <Side
            side={comparison.recommended}
            label={t('comparison.thisSeason')}
            highlight
          />
        </div>

        {/* Named, and directional.

            This was a bare "Difference on this plot" over a large red
            −₹55,705, which reads as a loss the farmer is about to take. It is
            neither a loss nor unexplained: it is how much less the
            recommendation earns than what they grew, and both crops have to be
            named or the number means nothing on its own. */}
        {difference != null && difference !== 0 && (
          <p className="mt-4 text-center text-sm">
            <span className="text-muted-foreground">
              {t(difference > 0 ? 'comparison.earnsMore' : 'comparison.earnsLess', {
                crop: cropName(
                  comparison.recommended.crop_code,
                  comparison.recommended.name,
                ),
                previous: cropName(
                  comparison.previous.crop_code,
                  comparison.previous.name,
                ),
              })}
            </span>
            <br />
            <span
              className={
                difference > 0
                  ? 'text-2xl font-semibold text-emerald-700'
                  : 'text-2xl font-semibold text-amber-700'
              }
            >
              {formatMoney(Math.abs(difference))}
            </span>
          </p>
        )}

        <p className="mt-4 flex items-start gap-2 rounded-md bg-muted p-3 text-sm">
          <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          <span>
            {serverText('verdict',
              comparison.verdict_code,
              comparison.verdict_params,
              comparison.verdict,
            )}
          </span>
        </p>

        <p className="mt-2 text-xs text-muted-foreground">{t('comparison.note')}</p>
      </CardContent>
    </Card>
  );
}
