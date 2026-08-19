'use client';

import { AlertTriangle, CalendarClock, ShieldCheck, TrendingUp } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatMoney, NOT_AVAILABLE } from '@/lib/format';
import { useI18n } from '@/i18n/provider';
import { useServerText } from '@/i18n/use-server-text';
import type { PriceOutlook } from '@/types/api';

/**
 * What the crop is likely to fetch when it is actually sold.
 *
 * The `basis` field decides how this renders, and that matters: a median over
 * recorded history and a statutory floor price are different kinds of claim.
 * Showing both as "expected price" would flatten that distinction and imply
 * confidence the data does not support.
 */
export function PriceOutlookCard({ outlook }: { outlook: PriceOutlook }) {
  const { t } = useI18n();
  const serverText = useServerText();

  const monthLabel = outlook.harvest_month
    ? new Intl.DateTimeFormat('en-IN', { month: 'long', year: 'numeric' }).format(
        new Date(`${outlook.harvest_month}-01T00:00:00Z`),
      )
    : null;

  const isForecast = outlook.basis === 'seasonal_history';

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <CalendarClock className="h-4 w-4 text-muted-foreground" aria-hidden />
            {monthLabel
              ? t('outlook.titleMonth', { month: monthLabel })
              : t('outlook.title')}
          </CardTitle>

          <Badge variant={isForecast ? 'positive' : 'outline'}>
            {isForecast
              ? t('outlook.basisHistory', { count: outlook.observations_used })
              : t('outlook.basisFloor')}
          </Badge>
        </div>
      </CardHeader>

      <CardContent>
        {isForecast ? (
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
            <div>
              <p className="text-xs text-muted-foreground">{t('outlook.expected')}</p>
              <p className="text-2xl font-semibold">
                {formatMoney(outlook.expected_per_quintal)}
                <span className="ml-1 text-sm font-normal text-muted-foreground">
                  {t('outlook.perQuintal')}
                </span>
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">{t('outlook.range')}</p>
              <p className="text-sm font-medium">
                {formatMoney(outlook.low_per_quintal)} – {formatMoney(outlook.high_per_quintal)}
              </p>
            </div>
          </div>
        ) : (
          // No usable history. Lead with the guarantee, not a guess.
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
            <div>
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
                {t('outlook.floor')}
              </p>
              <p className="text-2xl font-semibold">
                {outlook.msp_floor_per_quintal === null
                  ? NOT_AVAILABLE
                  : formatMoney(outlook.msp_floor_per_quintal)}
                <span className="ml-1 text-sm font-normal text-muted-foreground">
                  {t('outlook.perQuintal')}
                </span>
              </p>
            </div>
            <div>
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <TrendingUp className="h-3.5 w-3.5" aria-hidden />
                {t('outlook.today')}
              </p>
              <p className="text-sm font-medium">{formatMoney(outlook.current_per_quintal)}</p>
            </div>
          </div>
        )}

        {outlook.below_msp_by ? (
          <p className="mt-3 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>
            {serverText('outlook',
              outlook.explanation_code,
              outlook.explanation_params,
              outlook.explanation,
            )}
          </span>
          </p>
        ) : (
          <p className="mt-3 rounded-md bg-muted p-3 text-sm text-muted-foreground">
            {serverText('outlook',
              outlook.explanation_code,
              outlook.explanation_params,
              outlook.explanation,
            )}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
