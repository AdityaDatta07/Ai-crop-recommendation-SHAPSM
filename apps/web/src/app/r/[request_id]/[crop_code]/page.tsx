'use client';

import { use } from 'react';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfidenceBadge } from '@/components/recommendation/confidence-badge';
import { useRecommendationById } from '@/lib/queries';
import { userMessage } from '@/lib/api-error';
import {
  formatDateRange,
  formatMoney,
  formatNumber,
  NOT_AVAILABLE,
} from '@/lib/format';
import type { Economics } from '@/types/api';
import { useI18n } from '@/i18n/provider';
import { useCropName } from '@/i18n/use-crop-name';
import { useServerText } from '@/i18n/use-server-text';
import { PriceOutlookCard } from '@/components/recommendation/price-outlook-card';
import { SowingWindowNote } from '@/components/recommendation/sowing-window-note';
import { CounterfactualPanel } from '@/components/recommendation/counterfactual-panel';
import {
  UnitProvider,
  UnitToggle,
  useAreaUnit,
} from '@/components/recommendation/unit-toggle';

const IMPACT_VARIANT = {
  positive: 'positive',
  neutral: 'neutral',
  negative: 'negative',
} as const;

const SEVERITY_VARIANT: Record<string, 'neutral' | 'negative' | 'danger'> = {
  low: 'neutral',
  medium: 'negative',
  high: 'danger',
};

function EconomicsRow({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-border py-2 last:border-0">
      <div>
        <dt className="text-sm">{label}</dt>
        {note && <p className="text-xs text-muted-foreground">{note}</p>}
      </div>
      <dd
        className={
          value === NOT_AVAILABLE ? 'text-sm text-muted-foreground' : 'text-sm font-semibold'
        }
      >
        {value}
      </dd>
    </div>
  );
}

function EconomicsCard({
  economics,
  areaHa,
  areaAcres,
}: {
  economics: Economics;
  areaHa: number;
  areaAcres?: number | null;
}) {
  const { t } = useI18n();
  const serverText = useServerText();
  const { unit } = useAreaUnit();
  const incomplete = economics.net_margin === null;

  // Pick which pre-computed figure to show. Never convert here.
  const perUnitCost =
    unit === 'acre' ? economics.input_cost_per_acre : economics.input_cost_per_ha;
  const perUnitMargin = unit === 'acre' ? economics.margin_per_acre : economics.margin_per_ha;
  // The yield row used to stay in t/ha while the rows around it switched to
  // acres — three figures in two units, stacked.
  const perUnitYield =
    unit === 'acre' ? economics.expected_yield_t_acre : economics.expected_yield_t_ha;
  const unitSuffix = unit === 'acre' ? '/acre' : '/ha';
  const plotSize =
    unit === 'acre' && areaAcres != null
      ? `${formatNumber(areaAcres)} acres`
      : formatNumber(areaHa, 'ha');

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">{t('crop.money', { area: plotSize })}</CardTitle>
          <UnitToggle />
        </div>
      </CardHeader>
      <CardContent>
        <dl>
          <EconomicsRow
            label={t('crop.expectedYield')}
            value={formatNumber(perUnitYield, unit === 'acre' ? 't/acre' : 't/ha')}
            note={t('crop.yieldNote')}
          />
          <EconomicsRow
            label={t('crop.inputCost')}
            value={
              perUnitCost == null ? NOT_AVAILABLE : `${formatMoney(perUnitCost)}${unitSuffix}`
            }
          />
          <EconomicsRow
            label={t('crop.expectedPrice')}
            value={
              economics.expected_price_per_quintal === null
                ? NOT_AVAILABLE
                : `${formatMoney(economics.expected_price_per_quintal)}/quintal`
            }
          />
          <EconomicsRow label={t('crop.grossRevenue')} value={formatMoney(economics.gross_revenue)} />
          <EconomicsRow label={t('crop.netMargin')} value={formatMoney(economics.net_margin)} />
          <EconomicsRow
            label={unit === 'acre' ? t('crop.marginPerAcre') : t('crop.netMarginPerHa')}
            value={formatMoney(perUnitMargin)}
          />
        </dl>

        {incomplete && (
          <p className="mt-3 rounded-md bg-muted p-3 text-xs text-muted-foreground">
            {t('crop.priceUnavailable')}
          </p>
        )}

        {economics.price_source && (
          <p className="mt-3 text-xs text-muted-foreground">
            {t('crop.priceSource', { source: economics.price_source })}
            {economics.price_as_of ? ` (${economics.price_as_of})` : ''}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export default function CropDetailPage({
  params,
}: {
  params: Promise<{ request_id: string; crop_code: string }>;
}) {
  const cropName = useCropName();
  const { t } = useI18n();
  const serverText = useServerText();
  const { request_id: requestId, crop_code: cropCode } = use(params);
  const { data, isLoading, isError, error } = useRecommendationById(requestId);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <p className="on-canvas-muted flex items-center gap-2 text-sm">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          {t('results.loading')}
        </p>
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          {userMessage(error)}
        </div>
        <Link href="/">
          <Button variant="outline">{t('actions.startAgain')}</Button>
        </Link>
      </div>
    );
  }

  const crop = data.recommendations.find((item) => item.crop_code === cropCode);
  if (!crop) notFound();

  return (
    <UnitProvider>
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <Link
          href={`/r/${requestId}`}
          className="on-canvas-muted inline-flex items-center gap-1.5 text-sm transition-colors hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          {t('actions.allRecommendations')}
        </Link>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 className="on-canvas text-2xl font-semibold tracking-tight">
            {cropName(crop.crop_code, crop.name)}
          </h1>
          <Badge variant="secondary">Rank {crop.rank}</Badge>
          <ConfidenceBadge confidence={crop.confidence} />
        </div>

        {crop.variety_suggested && (
          <p className="on-canvas-muted mt-1">
            {t('crop.variety', { variety: crop.variety_suggested })}
          </p>
        )}
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">{t('crop.why')}</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-3">
            {crop.reasons.map((reason) => (
              <li key={`${reason.factor}-${reason.detail}`} className="space-y-1">
                <Badge variant={IMPACT_VARIANT[reason.impact as keyof typeof IMPACT_VARIANT] ?? 'neutral'}>
                  {t(`factors.${reason.factor}`)}
                </Badge>
                <p className="text-sm">
                  {serverText('reason', reason.code, reason.params, reason.detail)}
                </p>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <CounterfactualPanel
        counterfactuals={crop.counterfactuals ?? []}
        attribution={crop.attribution ?? []}
      />

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">{t('crop.calendar')}</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="space-y-2">
            <div className="flex justify-between gap-4 border-b border-border py-2">
              <dt className="text-sm text-muted-foreground">{t('crop.sowBetween')}</dt>
              <dd className="text-sm font-medium">
                {formatDateRange(crop.calendar.sowing_window.start, crop.calendar.sowing_window.end)}
              </dd>
            </div>
            <div className="flex justify-between gap-4 border-b border-border py-2">
              <dt className="text-sm text-muted-foreground">{t('crop.harvestAround')}</dt>
              <dd className="text-sm font-medium">
                {formatDateRange(
                  crop.calendar.harvest_window.start,
                  crop.calendar.harvest_window.end,
                )}
              </dd>
            </div>
            <div className="flex justify-between gap-4 py-2">
              <dt className="text-sm text-muted-foreground">{t('crop.timeInField')}</dt>
              <dd className="text-sm font-medium">
                {t('crop.days', { count: crop.calendar.duration_days })}
              </dd>
            </div>
          </dl>
          <SowingWindowNote calendar={crop.calendar} />
        </CardContent>
      </Card>

      {crop.price_outlook && <PriceOutlookCard outlook={crop.price_outlook} />}

      <EconomicsCard
        economics={crop.economics}
        areaHa={data.location_resolved.area_ha}
        areaAcres={data.location_resolved.area_acres}
      />

      {crop.risks.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{t('crop.risks')}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {crop.risks.map((risk) => (
                <li key={risk.name} className="flex flex-wrap items-center gap-2 text-sm">
                  <Badge variant={SEVERITY_VARIANT[risk.severity] ?? 'neutral'}>
                    {risk.severity}
                  </Badge>
                  <span className="font-medium">{risk.name}</span>
                  <span className="text-muted-foreground">({risk.type})</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-muted-foreground">
              {t('crop.risksNote')}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
    </UnitProvider>
  );
}
