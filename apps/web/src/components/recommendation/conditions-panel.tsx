'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatNumber, formatPercent, titleCase, NOT_AVAILABLE } from '@/lib/format';
import type { Conditions, ResolvedLocation } from '@/types/api';
import { useI18n } from '@/i18n/provider';
import { lookup, MESSAGES, type Locale } from '@/i18n';

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className={value === NOT_AVAILABLE ? 'text-sm text-muted-foreground' : 'text-sm font-medium'}>
        {value}
      </dd>
    </div>
  );
}

/** Soil classes arrive in English from OpenLandMap; server.term already has them. */
function soilTerm(locale: Locale, value: string | null | undefined): string {
  if (!value) return NOT_AVAILABLE;
  const key = `server.term.${value.toLowerCase().trim()}`;
  const translated = lookup(MESSAGES[locale], key);
  return translated === key ? titleCase(value) : translated;
}

export function ConditionsPanel({
  conditions,
  location,
  recorded = false,
}: {
  conditions: Conditions;
  location?: ResolvedLocation;
  /**
   * True when these figures came from a stored recording because the live
   * call could not be reached. Must be shown: a slow satellite service that
   * silently becomes plausible-looking sample data is worse than an error.
   */
  recorded?: boolean;
}) {
  const { t, locale } = useI18n();
  const { soil, weather } = conditions;

  return (
    <Card data-print-card>
      <CardHeader className="pb-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">
            {location
              ? t('conditions.headingFor', { district: location.district_name })
              : t('conditions.heading')}
          </CardTitle>
          <Badge variant="outline">
            {t('conditions.dataAvailable', { percent: formatPercent(conditions.data_completeness) })}
          </Badge>
        </div>
      </CardHeader>

      {/* Louder than a source line, because a substitution the reader cannot
          detect is the worst thing this app can do. The "(mocked)" suffix on
          the source string was already there and was missed — it looks like
          provenance, not a warning. */}
      {recorded && (
        <div className="px-6 pb-2">
          <p
            data-print-warning
            className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
          >
            {t('conditions.recorded')}
          </p>
        </div>
      )}

      <CardContent className="grid gap-6 sm:grid-cols-2">
        <div>
          <h3 className="mb-1 text-sm font-semibold">{t('conditions.soil')}</h3>
          <dl className="divide-y divide-border">
            <Row
              label={t('conditions.texture')}
              // Texture arrives from OpenLandMap as an English class name, so
              // it needs the same treatment as the sentences around it.
              value={soilTerm(locale, soil.texture)}
            />
            <Row label={t('conditions.ph')} value={formatNumber(soil.ph)} />
            <Row
              label={t('conditions.organicCarbon')}
              value={
                soil.organic_carbon_pct === null
                  ? NOT_AVAILABLE
                  : `${formatNumber(soil.organic_carbon_pct)}%`
              }
            />
            <Row label={t('conditions.nitrogen')} value={formatNumber(soil.nitrogen_kg_ha, 'kg/ha')} />
            <Row label={t('conditions.phosphorus')} value={formatNumber(soil.phosphorus_kg_ha, 'kg/ha')} />
            <Row label={t('conditions.potassium')} value={formatNumber(soil.potassium_kg_ha, 'kg/ha')} />
          </dl>
          {soil.source && (
            <p className="mt-2 text-xs text-muted-foreground">
              {t('conditions.source', { source: soil.source })}
            </p>
          )}
        </div>

        <div>
          <h3 className="mb-1 text-sm font-semibold">{t('conditions.weather')}</h3>
          <dl className="divide-y divide-border">
            <Row label={t('conditions.annualRainfall')} value={formatNumber(weather.annual_rainfall_mm, 'mm')} />
            <Row label={t('conditions.seasonRainfall')} value={formatNumber(weather.season_rainfall_mm, 'mm')} />
            <Row label={t('conditions.avgTemp')} value={formatNumber(weather.avg_temp_c, '°C')} />
            <Row label={t('conditions.ndvi')} value={formatNumber(conditions.ndvi_current)} />
          </dl>
          {weather.source && (
            <p className="mt-2 text-xs text-muted-foreground">
              {t('conditions.source', { source: weather.source })}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
