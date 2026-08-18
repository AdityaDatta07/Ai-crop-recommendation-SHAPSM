'use client';

import { use } from 'react';
import Link from 'next/link';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { CropCard } from '@/components/recommendation/crop-card';
import { ConditionsPanel } from '@/components/recommendation/conditions-panel';
import { WarningsList } from '@/components/recommendation/warnings-list';
import { useRecommendationById } from '@/lib/queries';
import { userMessage } from '@/lib/api-error';
import { formatNumber, formatTimestamp } from '@/lib/format';
import { useTranslation } from '@/i18n/provider';

export default function ResultsPage({ params }: { params: Promise<{ request_id: string }> }) {
  const t = useTranslation();
  const { request_id: requestId } = use(params);
  const { data, isLoading, isError, error } = useRecommendationById(requestId);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          {t('results.loading')}
        </p>
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-44 w-full" />
        ))}
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

  const { location_resolved: place, recommendations } = data;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          {t('actions.changeField')}
        </Link>

        <h1 className="mt-3 text-2xl font-semibold tracking-tight">
          {t('results.title', { district: place.district_name })}
        </h1>
        <p className="text-sm text-muted-foreground">
          {t('results.meta', {
            area: formatNumber(place.area_ha, 'ha'),
            state: place.state_code,
            timestamp: formatTimestamp(data.generated_at),
          })}
        </p>
      </div>

      <WarningsList warnings={data.warnings} />

      <ConditionsPanel conditions={data.conditions} location={place} />

      {recommendations.length === 0 ? (
        <p className="rounded-lg border border-border p-6 text-center text-muted-foreground">
          {t('results.empty')}
        </p>
      ) : (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            {t('results.ranked')}
          </h2>
          {recommendations.map((recommendation) => (
            <CropCard
              key={recommendation.crop_code}
              recommendation={recommendation}
              requestId={data.request_id}
            />
          ))}
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        {t('results.scoreCaveat')}
      </p>
    </div>
  );
}
