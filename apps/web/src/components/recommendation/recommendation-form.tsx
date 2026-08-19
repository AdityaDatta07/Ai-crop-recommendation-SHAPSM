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
import { MicButton } from '@/components/ui/mic-button';
import { parseArea } from '@/lib/voice-parse';
import { LocationPicker } from './location-picker';
import { ConditionsPanel } from './conditions-panel';
import { PrecisionNotice } from './precision-notice';
import { useCrops, useFieldSummary, useIndices, useRecommendations } from '@/lib/queries';
import { IndicesPanel } from '@/components/map/indices-panel';
import { CropHistoryPanel } from '@/components/map/crop-history-panel';
import { ProductivityPanel } from '@/components/map/productivity-panel';
import { userMessage } from '@/lib/api-error';
import type { Irrigation, Location, Season, SoilTest } from '@/types/api';
import { SoilTestFields } from './soil-test-fields';
import { acresToHectares, hectaresToAcres } from '@/lib/geometry';
import { useI18n } from '@/i18n/provider';
import { useCropName } from '@/i18n/use-crop-name';

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
  const { t, locale } = useI18n();

  const [location, setLocation] = useState<Location | null>(null);
  const [season, setSeason] = useState<Season>(defaultSeason);
  const [areaHa, setAreaHa] = useState('1');
  // Most Indian farmers know their plot in acres. The API takes hectares, so we
  // convert on entry — an input conversion, not a money calculation.
  const [areaUnit, setAreaUnit] = useState<'ha' | 'acre'>('ha');
  /** Why a spoken plot size was not used. Cleared by the next good one. */
  const [areaVoiceNote, setAreaVoiceNote] = useState<string | null>(null);
  const [previousCrop, setPreviousCrop] = useState('');
  const [irrigation, setIrrigation] = useState<Irrigation>('rainfed');
  const [soilTest, setSoilTest] = useState<SoilTest>({
    nitrogen_kg_ha: null,
    phosphorus_kg_ha: null,
    potassium_kg_ha: null,
  });

  const summary = useFieldSummary(location);
  const indices = useIndices(location);
  const crops = useCrops();
  const recommend = useRecommendations();

  const typedArea = Number.parseFloat(areaHa);
  const areaNumber = areaUnit === 'acre' ? acresToHectares(typedArea) : typedArea;
  const areaValid = Number.isFinite(areaNumber) && areaNumber > 0 && areaNumber <= 100;
  const canSubmit = location !== null && areaValid && !recommend.isPending;

  const areaError = useMemo(() => {
    if (areaHa === '') return null;
    if (!Number.isFinite(typedArea)) return t('season.areaNotNumber');
    if (areaNumber <= 0) return t('season.areaTooSmall');
    if (areaNumber > 100) return t('season.areaTooLarge');
    return null;
  }, [areaHa, typedArea, areaNumber, t]);

  /**
   * Fill the plot size from speech.
   *
   * The value lands in the input, visible and editable, rather than being
   * committed anywhere. Plot size multiplies straight into every rupee on the
   * results page, so a mishearing that is silently accepted is the one failure
   * this feature could cause that the farmer would never see.
   *
   * Bigha is refused rather than converted — it is between 1,600 and 6,000 m²
   * depending on the district. See lib/voice-parse.ts.
   */
  function heardArea(transcript: string) {
    const parsed = parseArea(transcript);
    if (!parsed.ok) {
      setAreaVoiceNote(t(`voice.area.${parsed.reason}`, { heard: transcript }));
      return;
    }
    setAreaVoiceNote(null);
    // Only move the toggle when a unit was actually spoken. "Two and a half"
    // should not silently reinterpret a farmer's earlier acre/hectare choice.
    if (parsed.unit) setAreaUnit(parsed.unit === 'acre' ? 'acre' : 'ha');
    setAreaHa(String(parsed.value));
  }

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
        ...(previousCrop ? { previous_crop: previousCrop } : {}),
        limit: 5,
      },
      { onSuccess: (data) => router.push(`/r/${data.request_id}`) },
    );
  }

  const cropName = useCropName();
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
          {summary.data && <PrecisionNotice location={summary.data.location_resolved} />}

          {summary.data && (
            <ConditionsPanel
              recorded={Boolean(summary.data.offline_recording)}
              conditions={summary.data.conditions}
              location={summary.data.location_resolved}
            />
          )}

          <IndicesPanel data={indices.data} isLoading={indices.isLoading} />

          {/* Read from the NDVI series the panel above already fetched, so it
              costs no extra satellite call. Shown here rather than on the
              results page because it describes the FIELD, and it is useful
              before a season has even been chosen. */}
          <CropHistoryPanel history={indices.data?.crop_history} locale={locale} />

          {/* Beside the history, because both answer "what is this plot like"
              rather than "what should I sow". */}
          <ProductivityPanel productivity={indices.data?.productivity} />
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
            {/* Wraps, and groups the two controls together.
                Flat, this row was Label + mic + unit toggle in a one-third
                grid column; on a laptop the three collided and the toggle
                overlapped the next field's heading. */}
            <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1.5">
              <Label htmlFor="area">{t('season.area')}</Label>
              <div className="flex items-center gap-1.5">
              <MicButton label={t('voice.sayArea')} onTranscript={heardArea} />
              <div className="inline-flex rounded border border-border p-0.5">
                {(['ha', 'acre'] as const).map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setAreaUnit(option)}
                    aria-pressed={areaUnit === option}
                    className={
                      areaUnit === option
                        ? 'rounded bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground'
                        : 'rounded px-2 py-0.5 text-xs font-medium text-muted-foreground'
                    }
                  >
                    {t(option === 'ha' ? 'season.areaUnitHa' : 'season.areaUnitAcre')}
                  </button>
                ))}
              </div>
              </div>
            </div>
            <Input
              id="area"
              inputMode="decimal"
              value={areaHa}
              aria-invalid={areaError !== null}
              onChange={(event) => setAreaHa(event.target.value)}
            />
            {areaError && <p className="text-sm text-destructive">{areaError}</p>}
            {areaVoiceNote && (
              <p className="text-xs text-muted-foreground" role="status">
                {areaVoiceNote}
              </p>
            )}
            {!areaError && Number.isFinite(typedArea) && typedArea > 0 && (
              <p className="text-xs text-muted-foreground">
                {t('season.areaEquals', {
                  value:
                    areaUnit === 'acre'
                      ? areaNumber.toFixed(2)
                      : hectaresToAcres(typedArea).toFixed(2),
                  unit: t(areaUnit === 'acre' ? 'season.areaUnitHa' : 'season.areaUnitAcre'),
                })}
              </p>
            )}
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

      <Card>
        <CardHeader>
          <CardTitle>{t('comparison.prompt')}</CardTitle>
          <CardDescription>{t('comparison.promptHelp')}</CardDescription>
        </CardHeader>
        <CardContent>
          <Select
            id="previous-crop"
            value={previousCrop}
            onChange={(event) => setPreviousCrop(event.target.value)}
          >
            <option value="">{t('comparison.none')}</option>
            {(crops.data?.crops ?? []).map((crop) => (
              <option key={crop.crop_code} value={crop.crop_code}>
                {cropName(crop.crop_code, crop.name)}
              </option>
            ))}
          </Select>
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
