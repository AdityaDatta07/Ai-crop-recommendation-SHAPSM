'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Calculator, Loader2, RotateCcw, TrendingDown, TrendingUp } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/client';
import { USE_MOCK_API } from '@/lib/config';
import { formatMoney, formatNumber, NOT_AVAILABLE } from '@/lib/format';
import { useI18n } from '@/i18n/provider';
import { useCropName } from '@/i18n/use-crop-name';
import { useAreaUnit } from './unit-toggle';
import type {
  Irrigation,
  RecommendationRequest,
  RecommendationResponse,
  RequestEcho,
  SoilTest,
} from '@/types/api';

/**
 * "What if my field were bigger, or I had a tubewell, or I applied more urea?"
 *
 * WHERE THE ARITHMETIC HAPPENS
 * ----------------------------
 * Not here. Every figure is produced by re-calling the recommendations
 * endpoint with the altered inputs, exactly the way the original was produced.
 *
 * The tempting shortcut is to multiply margin_per_ha by the new area in the
 * browser. It would be instant and it would be wrong: area changes which crops
 * clear a cost constraint, irrigation changes the rainfall score, and nitrogen
 * changes the ranking outright — so the top crop itself can change. A client
 * that multiplies would confidently show the old crop's margin at a new size.
 * Worse, it would become a second place money is calculated, and the two would
 * eventually disagree. architecture.md: every number has one source.
 *
 * WHAT THIS DOES NOT DO
 * ---------------------
 * It does not overwrite the advisory. The saved result and its shareable link
 * keep the inputs the farmer actually gave. This panel is a sandbox, and Reset
 * puts it back.
 */

const DEBOUNCE_MS = 500;

/** kg/ha. Wide enough for real Soil Health Cards, tight enough to catch a slip. */
const NUTRIENT_MAX = { nitrogen: 800, phosphorus: 200, potassium: 800 } as const;

const IRRIGATION_OPTIONS: Irrigation[] = ['rainfed', 'canal', 'tubewell', 'drip'];

interface Draft {
  areaHa: number;
  irrigation: Irrigation;
  nitrogen: number | null;
  phosphorus: number | null;
  potassium: number | null;
}

function draftFromEcho(echo: RequestEcho): Draft {
  return {
    areaHa: echo.area_ha,
    irrigation: echo.irrigation ?? 'rainfed',
    nitrogen: echo.soil_test?.nitrogen_kg_ha ?? null,
    phosphorus: echo.soil_test?.phosphorus_kg_ha ?? null,
    potassium: echo.soil_test?.potassium_kg_ha ?? null,
  };
}

function draftToRequest(echo: RequestEcho, draft: Draft): RecommendationRequest {
  // All three keys are always sent, null included: null means "no reading",
  // which is a different claim from "not mentioned" and the API treats it so.
  const soilTest: SoilTest | undefined =
    draft.nitrogen === null && draft.phosphorus === null && draft.potassium === null
      ? undefined
      : {
          nitrogen_kg_ha: draft.nitrogen,
          phosphorus_kg_ha: draft.phosphorus,
          potassium_kg_ha: draft.potassium,
        };

  return {
    location: echo.location,
    season: echo.season,
    area_ha: draft.areaHa,
    irrigation: draft.irrigation,
    soil_test: soilTest,
    previous_crop: echo.previous_crop ?? undefined,
  };
}

function sameDraft(a: Draft, b: Draft): boolean {
  return (
    Math.abs(a.areaHa - b.areaHa) < 0.0001 &&
    a.irrigation === b.irrigation &&
    a.nitrogen === b.nitrogen &&
    a.phosphorus === b.phosphorus &&
    a.potassium === b.potassium
  );
}

// --------------------------------------------------------------------- inputs

function SliderRow({
  label,
  value,
  min,
  max,
  step,
  suffix,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  suffix: string;
  onChange: (next: number) => void;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <label className="text-sm font-medium">{label}</label>
        <span className="font-mono text-sm">
          {formatNumber(value, suffix)}
        </span>
      </div>
      <input
        type="range"
        className="mt-1.5 w-full accent-primary"
        min={min}
        max={max}
        step={step}
        value={value}
        aria-label={label}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </div>
  );
}

// --------------------------------------------------------------------- result

function Delta({ current, baseline }: { current: number | null; baseline: number | null }) {
  const { t } = useI18n();
  if (current === null || baseline === null) return null;

  const difference = current - baseline;
  // A rounding-level wobble is not a change worth an arrow.
  if (Math.abs(difference) < 1) {
    return <span className="text-xs text-muted-foreground">{t('impact.noChange')}</span>;
  }

  const up = difference > 0;
  const Icon = up ? TrendingUp : TrendingDown;
  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-medium ${
        up ? 'text-emerald-700' : 'text-red-700'
      }`}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {up ? '+' : '−'}
      {formatMoney(Math.abs(difference))}
    </span>
  );
}

// ----------------------------------------------------------------------- main

export function ImpactCalculator({ result }: { result: RecommendationResponse }) {
  const { t } = useI18n();
  const cropName = useCropName();
  const { unit } = useAreaUnit();

  const echo = result.request_echo;
  const baseline = useMemo(() => (echo ? draftFromEcho(echo) : null), [echo]);

  const [draft, setDraft] = useState<Draft | null>(baseline);
  const [preview, setPreview] = useState<RecommendationResponse | null>(null);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  const requestSeq = useRef(0);

  useEffect(() => {
    if (!echo || !draft || !baseline) return;

    // Back at the original inputs: show the real advisory, do not re-ask for it.
    if (sameDraft(draft, baseline)) {
      setPreview(null);
      setPending(false);
      setFailed(false);
      return;
    }

    setPending(true);
    setFailed(false);
    const seq = ++requestSeq.current;

    const timer = setTimeout(() => {
      api
        .postRecommendations(draftToRequest(echo, draft))
        .then((next) => {
          // Slider drags produce overlapping requests; only the newest may win,
          // or an early reply lands after a later one and the panel shows a
          // number that belongs to inputs the farmer has already moved past.
          if (seq !== requestSeq.current) return;
          setPreview(next);
          setPending(false);
        })
        .catch(() => {
          if (seq !== requestSeq.current) return;
          setFailed(true);
          setPending(false);
        });
    }, DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [draft, echo, baseline]);

  // An older saved result has no request_echo, so there is nothing to vary.
  // Hiding the panel is right: a calculator that cannot recalculate is worse
  // than no calculator.
  if (!echo || !draft || !baseline) return null;

  const shown = preview ?? result;
  const top = shown.recommendations[0];
  const baselineTop = result.recommendations[0];
  if (!top || !baselineTop) return null;

  const changed = !sameDraft(draft, baseline);
  const cropChanged = changed && top.crop_code !== baselineTop.crop_code;

  // The headline has to be the WHOLE-PLOT total, not the per-hectare rate.
  //
  // margin_per_ha is a rate: it is invariant to area by construction, and
  // apps/api/tests/test_impact_calculator.py asserts that it is. Putting it
  // under a plot-size slider meant dragging from 1 ha to 2.5 ha left the number
  // untouched — which reads as "more land earns you nothing" rather than "you
  // are looking at a per-hectare figure".
  //
  // The rate still earns its place below, because it is the number that
  // responds to irrigation and nutrients but not to area, and seeing the two
  // move independently is the clearest way to understand why.
  const total = top.economics.net_margin;
  const baseTotal = baselineTop.economics.net_margin;
  const rate = unit === 'acre' ? top.economics.margin_per_acre : top.economics.margin_per_ha;
  const unitLabel = t(unit === 'acre' ? 'crop.unitAcre' : 'crop.unitHectare');

  const update = (patch: Partial<Draft>) => setDraft((current) => ({ ...current!, ...patch }));

  return (
    <Card className="no-print">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Calculator className="h-4 w-4 text-muted-foreground" aria-hidden />
          {t('impact.title')}
        </CardTitle>
        <p className="text-sm text-muted-foreground">{t('impact.help')}</p>
      </CardHeader>

      <CardContent>
        {USE_MOCK_API && (
          // Mock mode replays a fixed 1 ha recording, so the plot-size slider
          // would move and nothing would change. Say so rather than letting a
          // farmer conclude that doubling their land earns them nothing.
          <p className="mb-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            {t('impact.mockNotice')}
          </p>
        )}

        <div className="grid gap-5 sm:grid-cols-2">
          <SliderRow
            label={t('impact.plotSize')}
            value={draft.areaHa}
            min={0.1}
            // The form accepts up to 100 ha. A fixed max of 20 would clamp a
            // larger field to the end of the track and quietly show it as 20.
            max={Math.max(20, Math.ceil(baseline.areaHa * 2))}
            step={0.1}
            suffix={t('season.areaUnitHa')}
            onChange={(areaHa) => update({ areaHa })}
          />

          <div>
            <label className="text-sm font-medium">{t('impact.irrigation')}</label>
            <div className="mt-1.5 inline-flex flex-wrap gap-1 rounded-md border border-border p-0.5">
              {IRRIGATION_OPTIONS.map((option) => (
                <button
                  key={option}
                  type="button"
                  aria-pressed={draft.irrigation === option}
                  onClick={() => update({ irrigation: option })}
                  className={`rounded px-2.5 py-1 text-xs ${
                    draft.irrigation === option
                      ? 'bg-primary text-primary-foreground'
                      : 'text-muted-foreground hover:bg-muted'
                  }`}
                >
                  {t(`season.${option}`)}
                </button>
              ))}
            </div>
          </div>

          {(['nitrogen', 'phosphorus', 'potassium'] as const).map((nutrient) => (
            <SliderRow
              key={nutrient}
              label={t(`impact.${nutrient}`)}
              value={draft[nutrient] ?? 0}
              min={0}
              max={NUTRIENT_MAX[nutrient]}
              step={10}
              suffix="kg/ha"
              onChange={(next) => update({ [nutrient]: next } as Partial<Draft>)}
            />
          ))}
        </div>

        {/* ------------------------------------------------------- outcome */}
        <div className="mt-5 rounded-lg border border-border bg-muted/40 p-4">
          {failed ? (
            <p className="text-sm text-muted-foreground">{t('impact.failed')}</p>
          ) : (
            <>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-sm text-muted-foreground">{t('impact.bestCrop')}</span>
                <span className="flex items-center gap-2 font-semibold">
                  {cropName(top.crop_code, top.name)}
                  {cropChanged && <Badge variant="outline">{t('impact.cropChanged')}</Badge>}
                </span>
              </div>

              <div className="mt-2 flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-sm text-muted-foreground">
                  {t('impact.netMarginPlot')}{' '}
                  <span className="text-xs">
                    ({formatNumber(draft.areaHa, t('season.areaUnitHa'))})
                  </span>
                </span>
                <span className="flex items-center gap-2">
                  {/* Dimmed while in flight: the number on screen belongs to the
                      previous inputs until the new answer arrives. Showing it
                      crisply would be a lie for about half a second. */}
                  <span
                    className={`font-mono text-lg font-semibold ${pending ? 'opacity-40' : ''}`}
                  >
                    {total === null || total === undefined ? NOT_AVAILABLE : formatMoney(total)}
                  </span>
                  {pending ? (
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-hidden />
                  ) : (
                    changed && <Delta current={total ?? null} baseline={baseTotal ?? null} />
                  )}
                </span>
              </div>

              {/* The rate, stated as a rate. Unaffected by the plot-size
                  slider, and that is the correct behaviour once it is labelled
                  honestly. */}
              <div className="mt-1 flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-xs text-muted-foreground">
                  {t('impact.netMarginRate', { unit: unitLabel })}
                </span>
                <span className={`font-mono text-sm ${pending ? 'opacity-40' : ''}`}>
                  {rate === null || rate === undefined ? NOT_AVAILABLE : formatMoney(rate)}
                </span>
              </div>

              <div className="mt-1 flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-xs text-muted-foreground">{t('crop.expectedYield')}</span>
                <span className={`font-mono text-sm ${pending ? 'opacity-40' : ''}`}>
                  {formatNumber(top.economics.expected_yield_t_ha, 't/ha')}
                </span>
              </div>

              {changed && (
                <p className="mt-3 border-t border-border pt-2 text-xs text-muted-foreground">
                  {t('impact.comparedTo')}
                </p>
              )}
            </>
          )}
        </div>

        <div className="mt-3 flex items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">{t('impact.note')}</p>
          {changed && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setDraft(baseline)}
              className="shrink-0"
            >
              <RotateCcw className="mr-1.5 h-3.5 w-3.5" aria-hidden />
              {t('impact.reset')}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
