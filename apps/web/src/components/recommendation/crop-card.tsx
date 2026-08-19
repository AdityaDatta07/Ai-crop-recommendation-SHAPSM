'use client';

import Link from 'next/link';
import { ChevronRight } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ConfidenceBadge } from './confidence-badge';
import { formatMoney, formatNumber, NOT_AVAILABLE } from '@/lib/format';
import type { Recommendation } from '@/types/api';
import { useI18n } from '@/i18n/provider';
import { useCropName } from '@/i18n/use-crop-name';
import { useServerText } from '@/i18n/use-server-text';

const IMPACT_VARIANT = {
  positive: 'positive',
  neutral: 'neutral',
  negative: 'negative',
} as const;

export function CropCard({
  recommendation,
  requestId,
}: {
  recommendation: Recommendation;
  requestId: string;
}) {
  const cropName = useCropName();
  const { t } = useI18n();
  const serverText = useServerText();
  const { economics } = recommendation;

  return (
    <Card data-print-card className="transition-colors hover:border-primary/40">
      <CardContent className="p-5">
        <Link
          href={`/r/${requestId}/${recommendation.crop_code}`}
          className="flex items-start justify-between gap-3"
        >
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
                {recommendation.rank}
              </span>
              <h2 className="text-lg font-semibold">
                {cropName(recommendation.crop_code, recommendation.name)}
              </h2>
            </div>
            {recommendation.variety_suggested && (
              <p className="mt-1 text-sm text-muted-foreground">
                {t('crop.variety', { variety: recommendation.variety_suggested })}
              </p>
            )}
          </div>
          <ChevronRight className="mt-1 h-5 w-5 shrink-0 text-muted-foreground" aria-hidden />
        </Link>

        <div className="mt-3 flex flex-wrap gap-2">
          <ConfidenceBadge confidence={recommendation.confidence} />
          <Badge variant="outline" title="Relative to the other crops in this result only">
            {t('crop.suitability', { score: Math.round(recommendation.score * 100) })}
          </Badge>
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
          <div>
            <dt className="text-xs text-muted-foreground">{t('crop.expectedYield')}</dt>
            <dd className="text-sm font-medium">
              {formatNumber(economics.expected_yield_t_ha, 't/ha')}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">{t('crop.inputCost')}</dt>
            <dd className="text-sm font-medium">
              {economics.input_cost_per_ha === null
                ? NOT_AVAILABLE
                : `${formatMoney(economics.input_cost_per_ha)}/ha`}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">{t('crop.netMargin')}</dt>
            <dd className="text-sm font-medium">{formatMoney(economics.net_margin)}</dd>
          </div>
        </dl>

        <ul className="mt-4 space-y-1.5">
          {recommendation.reasons.slice(0, 3).map((reason) => (
            <li key={`${reason.factor}-${reason.detail}`} className="flex flex-wrap items-baseline gap-2 text-sm">
              <Badge variant={IMPACT_VARIANT[reason.impact as keyof typeof IMPACT_VARIANT] ?? 'neutral'}>
                {t(`factors.${reason.factor}`)}
              </Badge>
              <span className="text-muted-foreground">
                {serverText('reason', reason.code, reason.params, reason.detail)}
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
