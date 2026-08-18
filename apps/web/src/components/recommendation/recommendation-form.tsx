'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { LocationPicker } from './location-picker';
import { ConditionsPanel } from './conditions-panel';
import { useFieldSummary, useIndices, useRecommendations } from '@/lib/queries';
import { IndicesPanel } from '@/components/map/indices-panel';
import { userMessage } from '@/lib/api-error';
import type { Irrigation, Location, Season, SoilTest } from '@/types/api';
import { SoilTestFields } from './soil-test-fields';
import { useTranslation } from '@/i18n/provider';

const SEASONS: Season[] = ['kharif', 'rabi', 'zaid'];
const IRRIGATION: Irrigation[] = ['rainfed', 'canal', 'tubewell', 'drip'];

/** The season a farmer is most likely planning for right now. */
function defaultSeason(): Season {
  const month = new Date().getMonth() + 1;
  if (month >= 6 && month <= 9) return 'kharif';
  if (month >= 10 || month <= 2) return 'rabi';
  return 'zaid';
}

export function RecommendationForm() {
  const router = useRouter();
  const t = useTranslation();

  const [location, setLocation] = useState<Location | null>(null);
  const [season, setSeason] = useState<Season>(defaultSeason);
  const [areaHa, setAreaHa] = useState('1');
  const [irrigation, setIrrigation] = useState<Irrigation>('rainfed');
  const [soilTest, setSoilTest] = useState<SoilTest>({
    nitrogen_kg_ha: null,
    phosphorus_kg_ha: null,
    potassium_kg_ha: null,
  });

  const summary = useFieldSummary(location);
  const indices = useIndices(location);
  const recommend = useRecommendations();

  const areaNumber = Number.parseFloat(areaHa);
  const areaValid = Number.isFinite(areaNumber) && areaNumber > 0 && areaNumber <= 100;
  const canSubmit = location !== null && areaValid && !recommend.isPending;

  const areaError = useMemo(() => {
    if (areaHa === '') return null;
    if (!Number.isFinite(areaNumber)) return t('season.areaNotNumber');
    if (areaNumber <= 0) return t('season.areaTooSmall');
    if (areaNumber > 100) return t('season.areaTooLarge');
    return null;
  }, [areaHa, areaNumber, t]);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!location || !areaValid) return;

    recommend.mutate(
      {
        location,
        season,
        area_ha: areaNumber,
        irrigation,
        // Omit entirely when empty, so the request says nothing rather than
        // sending three nulls the API has to interpret.
        ...(Object.values(soilTest).some((v) => v !== null) ? { soil_test: soilTest } : {}),
        limit: 5,
      },
      { onSuccess: (data) => router.push(`/r/${data.request_id}`) },
    );
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t('location.heading')}</CardTitle>
          <CardDescription>{t('location.help')}</CardDescription>
        </CardHeader>
        <CardContent>
          <LocationPicker
            value={location}
            onChange={setLocation}
            tileUrlTemplate={indices.data?.tile_url_template}
          />
        </CardContent>
      </Card>

      {location && (
        <>
          {summary.isLoading && (
            <Card>
              <CardContent className="space-y-3 p-5">
                <Skeleton className="h-4 w-48" />
                <Skeleton className="h-24 w-full" />
                <p className="text-sm text-muted-foreground">{t('conditions.reading')}</p>
              </CardContent>
            </Card>
          )}
          {summary.data && (
            <ConditionsPanel
              conditions={summary.data.conditions}
              location={summary.data.location_resolved}
            />
          )}

          <IndicesPanel data={indices.data} isLoading={indices.isLoading} />
        </>
      )}

      <Card>
        <CardHeader>
          <CardTitle>{t('season.heading')}</CardTitle>
          <CardDescription>{t('season.help')}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="season">{t('season.label')}</Label>
            <Select
              id="season"
              value={season}
              onChange={(event) => setSeason(event.target.value as Season)}
            >
              {SEASONS.map((option) => (
                <option key={option} value={option}>
                  {t(`season.${option}`)} — {t(`season.${option}Hint`)}
                </option>
              ))}
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="area">{t('season.area')}</Label>
            <Input
              id="area"
              inputMode="decimal"
              value={areaHa}
              aria-invalid={areaError !== null}
              onChange={(event) => setAreaHa(event.target.value)}
            />
            {areaError && <p className="text-sm text-destructive">{areaError}</p>}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="irrigation">{t('season.water')}</Label>
            <Select
              id="irrigation"
              value={irrigation}
              onChange={(event) => setIrrigation(event.target.value as Irrigation)}
            >
              {IRRIGATION.map((option) => (
                <option key={option} value={option}>
                  {t(`season.${option}`)}
                </option>
              ))}
            </Select>
          </div>
        </CardContent>
      </Card>

      <SoilTestFields value={soilTest} onChange={setSoilTest} />

      {recommend.isError && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          {userMessage(recommend.error)}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" size="lg" disabled={!canSubmit}>
          {recommend.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          ) : (
            <Search className="h-4 w-4" aria-hidden />
          )}
          {recommend.isPending ? t('actions.submitting') : t('actions.submit')}
        </Button>

        {recommend.isPending && (
          <p className="text-sm text-muted-foreground">{t('actions.slowHint')}</p>
        )}
      </div>
    </form>
  );
}
