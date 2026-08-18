'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { NOT_AVAILABLE, formatDate, formatNumber } from '@/lib/format';
import { useTranslation } from '@/i18n/provider';
import type { IndicesResponse } from '@/types/api';

/** Where a value sits inside its own range, as a 0-100 bar width. */
function positionPct(value: number, min: number, max: number): number {
  return Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
}

function NdviHistory({ points }: { points: IndicesResponse['history'] }) {
  const t = useTranslation();
  const usable = points.filter((p) => p.ndvi !== null);
  if (usable.length < 2) return null;

  const width = 100;
  const height = 28;
  const path = usable
    .map((point, index) => {
      const x = (index / (usable.length - 1)) * width;
      // NDVI 0-1 maps to full height, inverted because SVG y grows downward.
      const y = height - (point.ndvi as number) * height;
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');

  return (
    <div className="mt-4 border-t border-border pt-4">
      <h4 className="text-sm font-semibold">{t('indices.historyTitle')}</h4>
      <p className="mt-0.5 text-xs text-muted-foreground">{t('indices.historyHelp')}</p>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="mt-2 h-16 w-full"
        role="img"
        aria-label={t('indices.historyTitle')}
      >
        <path d={path} fill="none" stroke="hsl(var(--primary))" strokeWidth="1" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{formatDate(usable[0].date)}</span>
        <span>{formatDate(usable[usable.length - 1].date)}</span>
      </div>
    </div>
  );
}

export function IndicesPanel({
  data,
  isLoading,
}: {
  data: IndicesResponse | undefined;
  isLoading: boolean;
}) {
  const t = useTranslation();

  if (isLoading) {
    return (
      <Card>
        <CardContent className="space-y-3 p-5">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-28 w-full" />
          <p className="text-sm text-muted-foreground">{t('indices.loading')}</p>
        </CardContent>
      </Card>
    );
  }

  if (!data) return null;

  const stale = data.observed_on === null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">{t('indices.title')}</CardTitle>
          {data.observed_on && (
            <Badge variant="outline">
              {t('indices.observed', { date: formatDate(data.observed_on) })}
            </Badge>
          )}
        </div>
        {data.cloud_cover_pct !== null && (
          <p className="text-xs text-muted-foreground">
            {t('indices.cloud', { percent: formatNumber(data.cloud_cover_pct) })}
          </p>
        )}
      </CardHeader>

      <CardContent>
        {stale ? (
          <p className="rounded-md bg-muted p-3 text-sm text-muted-foreground">
            {t('indices.unavailable')}
          </p>
        ) : (
          <ul className="space-y-4">
            {data.indices.map((index) => (
              <li key={index.key}>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-sm font-medium">{index.name}</span>
                  <span className={index.value === null ? 'text-sm text-muted-foreground' : 'text-sm font-semibold'}>
                    {index.value === null ? NOT_AVAILABLE : index.value.toFixed(2)}
                  </span>
                </div>

                {index.value !== null && (
                  <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{ width: `${positionPct(index.value, index.range_min, index.range_max)}%` }}
                    />
                  </div>
                )}

                <p className="mt-1 text-xs text-muted-foreground">{index.interpretation}</p>
                <p className="mt-0.5 font-mono text-[10px] text-muted-foreground/70">{index.formula}</p>
              </li>
            ))}
          </ul>
        )}

        <NdviHistory points={data.history} />

        <p className="mt-4 text-xs text-muted-foreground">
          {t('conditions.source', { source: data.source })}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">{t('indices.caveat')}</p>
      </CardContent>
    </Card>
  );
}
