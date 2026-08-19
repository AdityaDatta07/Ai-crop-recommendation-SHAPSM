'use client';

import { useCallback, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { Crosshair, Loader2, MapPin } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { MicButton } from '@/components/ui/mic-button';
import { cn } from '@/lib/utils';
import { matchDistrict, type DistrictOption } from '@/lib/voice-parse';
import { useDistricts } from '@/lib/queries';
import type { IndicesResponse, Location, LonLat } from '@/types/api';
import { closedRing, validateRing } from '@/lib/geometry';
import { useTranslation } from '@/i18n/provider';

type Mode = 'district' | 'point' | 'map';

// MapLibre touches window on import, so it cannot be server-rendered.
const FieldMap = dynamic(() => import('@/components/map/field-map').then((m) => m.FieldMap), {
  ssr: false,
  loading: () => <div className="h-[360px] w-full animate-pulse rounded-lg bg-muted" />,
});

/**
 * Two of the three location forms in the contract. The `polygon` form needs the
 * MapLibre draw surface and is deliberately not stubbed here - a disabled tab
 * would promise something the API path has not been exercised against yet.
 */
export function LocationPicker({
  value,
  onChange,
  tileUrlTemplate,
}: {
  value: Location | null;
  onChange: (location: Location | null) => void;
  /** Sentinel-2 overlay for the map tab, when the API supplies one. */
  tileUrlTemplate?: string | null;
}) {
  const t = useTranslation();
  const [mode, setMode] = useState<Mode>('district');
  const [stateCode, setStateCode] = useState('');
  const [lat, setLat] = useState('');
  const [lon, setLon] = useState('');
  const [locating, setLocating] = useState(false);
  const [ring, setRing] = useState<LonLat[]>([]);
  const [geoError, setGeoError] = useState<string | null>(null);
  /** What the recogniser heard, when it matched no district on the list. */
  const [heardMiss, setHeardMiss] = useState<string | null>(null);

  const { data, isLoading, isError } = useDistricts();
  const states = data?.states ?? [];
  const districts = states.find((s) => s.state_code === stateCode)?.districts ?? [];

  function switchMode(next: Mode) {
    setMode(next);
    onChange(null);
  }

  // A ring is only a usable location once it is a valid closed polygon; below
  // three corners we hold the drawing but report no location upward.
  const handleRing = useCallback(
    (next: LonLat[]) => {
      setRing(next);
      if (next.length < 3 || validateRing(next) !== null) {
        onChange(null);
        return;
      }
      onChange({
        type: 'polygon',
        geometry: { type: 'Polygon', coordinates: [closedRing(next)] },
      });
    },
    [onChange],
  );

  function selectDistrict(districtCode: string) {
    onChange(districtCode ? { type: 'admin', state_code: stateCode, district_code: districtCode } : null);
  }

  /**
   * Voice searches every state at once, and sets the state dropdown itself.
   *
   * A farmer says "Lucknow", not "Uttar Pradesh, then Lucknow". Requiring the
   * state first would mean reading a dropdown, which is the thing the
   * microphone exists to avoid.
   */
  const allDistricts = useMemo(
    () =>
      (data?.states ?? []).flatMap((state) =>
        state.districts.map((district) => ({
          district_code: district.district_code,
          district_name: district.district_name,
          state_code: state.state_code,
        })),
      ),
    [data],
  );

  function heardDistrict(transcript: string) {
    const match = matchDistrict(transcript, allDistricts);
    if (!match) {
      // Show what was heard. "Not found" alone leaves the farmer guessing
      // whether they spoke unclearly or the district is simply missing.
      setHeardMiss(transcript);
      return;
    }
    setHeardMiss(null);
    setStateCode(match.state_code);
    onChange({
      type: 'admin',
      state_code: match.state_code,
      district_code: match.district_code,
    });
  }

  function commitPoint(nextLat: string, nextLon: string) {
    const latNum = Number.parseFloat(nextLat);
    const lonNum = Number.parseFloat(nextLon);
    const valid =
      Number.isFinite(latNum) &&
      Number.isFinite(lonNum) &&
      latNum >= -90 &&
      latNum <= 90 &&
      lonNum >= -180 &&
      lonNum <= 180;
    onChange(valid ? { type: 'point', lat: latNum, lon: lonNum } : null);
  }

  function useMyLocation() {
    if (!('geolocation' in navigator)) {
      setGeoError(t('location.geoUnsupported'));
      return;
    }
    setLocating(true);
    setGeoError(null);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const nextLat = position.coords.latitude.toFixed(5);
        const nextLon = position.coords.longitude.toFixed(5);
        setLat(nextLat);
        setLon(nextLon);
        commitPoint(nextLat, nextLon);
        setLocating(false);
      },
      () => {
        setGeoError(t('location.geoDenied'));
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }

  const selectedDistrict = value?.type === 'admin' ? value.district_code : '';

  return (
    <div className="space-y-4">
      <div className="inline-flex rounded-md border border-border p-1" role="tablist">
        {(['district', 'point', 'map'] as const).map((option) => (
          <button
            key={option}
            type="button"
            role="tab"
            aria-selected={mode === option}
            onClick={() => switchMode(option)}
            className={cn(
              'rounded px-4 py-1.5 text-sm font-medium transition-colors',
              mode === option ? 'bg-primary text-primary-foreground' : 'text-muted-foreground',
            )}
          >
            {option === 'district'
              ? t('location.tabDistrict')
              : option === 'point'
                ? t('location.tabPoint')
                : t('map.tab')}
          </button>
        ))}
      </div>

      {mode === 'map' ? (
        <FieldMap ring={ring} onChange={handleRing} tileUrlTemplate={tileUrlTemplate} />
      ) : mode === 'district' ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="state">{t('location.state')}</Label>
            <Select
              id="state"
              value={stateCode}
              disabled={isLoading || isError}
              onChange={(event) => {
                setStateCode(event.target.value);
                onChange(null);
              }}
            >
              <option value="">{isLoading ? t('location.loading') : t('location.selectState')}</option>
              {states.map((state) => (
                <option key={state.state_code} value={state.state_code}>
                  {state.state_name}
                </option>
              ))}
            </Select>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <Label htmlFor="district">{t('location.district')}</Label>
              {/* Searches every state, so it is offered even before one is
                  chosen — unlike the dropdown beside it. */}
              <MicButton
                label={t('voice.sayDistrict')}
                onTranscript={heardDistrict}
                disabled={isLoading || isError}
              />
            </div>
            <Select
              id="district"
              value={selectedDistrict}
              disabled={!stateCode}
              onChange={(event) => selectDistrict(event.target.value)}
            >
              <option value="">
                {stateCode ? t('location.selectDistrict') : t('location.pickStateFirst')}
              </option>
              {districts.map((district) => (
                <option key={district.district_code} value={district.district_code}>
                  {district.district_name}
                </option>
              ))}
            </Select>
          </div>

          {heardMiss && (
            <p className="text-sm text-muted-foreground sm:col-span-2" role="status">
              {t('voice.districtMiss', { heard: heardMiss })}
            </p>
          )}

          {isError && (
            <p className="text-sm text-destructive sm:col-span-2">
              {t('location.districtListUnavailable')}
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="lat">{t('location.latitude')}</Label>
              <Input
                id="lat"
                inputMode="decimal"
                placeholder="26.8467"
                value={lat}
                onChange={(event) => {
                  setLat(event.target.value);
                  commitPoint(event.target.value, lon);
                }}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="lon">{t('location.longitude')}</Label>
              <Input
                id="lon"
                inputMode="decimal"
                placeholder="80.9462"
                value={lon}
                onChange={(event) => {
                  setLon(event.target.value);
                  commitPoint(lat, event.target.value);
                }}
              />
            </div>
          </div>

          <Button type="button" variant="outline" onClick={useMyLocation} disabled={locating}>
            {locating ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            ) : (
              <Crosshair className="h-4 w-4" aria-hidden />
            )}
            {t('location.useMyLocation')}
          </Button>

          {geoError && <p className="text-sm text-destructive">{geoError}</p>}
        </div>
      )}

      {value && (
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <MapPin className="h-4 w-4" aria-hidden />
          {value.type === 'admin'
            ? `District ${value.district_code}`
            : value.type === 'point'
              ? `${value.lat}, ${value.lon}`
              : t('location.drawnBoundary')}
        </p>
      )}
    </div>
  );
}
