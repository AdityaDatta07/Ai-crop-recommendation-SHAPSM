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
import { useTranslation } from '@/i18n/provider';

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

function EconomicsCard({ economics, areaHa }: { economics: Economics; areaHa: number }) {
  const t = useTranslation();
  const incomplete = economics.net_margin === null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">
          {t('crop.money', { area: formatNumber(areaHa, 'ha') })}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <dl>
          <EconomicsRow
            label={t('crop.expectedYield')}
            value={formatNumber(economics.expected_yield_t_ha, 't/ha')}
            note={t('crop.yieldNote')}
          />
          <EconomicsRow
            label={t('crop.inputCost')}
            value={
              economics.input_cost_per_ha === null
                ? NOT_AVAILABLE
                : `${formatMoney(economics.input_cost_per_ha)}/ha`
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
            label={t('crop.netMarginPerHa')}
            value={formatMoney(economics.margin_per_ha)}
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
  const t = useTranslation();
  const { request_id: requestId, crop_code: cropCode } = use(params);
  const { data, isLoading, isError, error } = useRecommendationById(requestId);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
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
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <Link
          href={`/r/${requestId}`}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          {t('actions.allRecommendations')}
        </Link>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{crop.name}</h1>
          <Badge variant="secondary">Rank {crop.rank}</Badge>
          <ConfidenceBadge confidence={crop.confidence} />
        </div>

        {crop.variety_suggested && (
          <p className="mt-1 text-muted-foreground">
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
                <p className="text-sm">{reason.detail}</p>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

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
        </CardContent>
      </Card>

      <EconomicsCard economics={crop.economics} areaHa={data.location_resolved.area_ha} />

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
  );
}
