'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import maplibregl, { type Map as MapLibreMap } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { Crosshair, Trash2, Undo2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { centroid, closedRing, polygonAreaHa, validateRing } from '@/lib/geometry';
import { useTranslation } from '@/i18n/provider';
import type { LonLat } from '@/types/api';

const DRAWN_SOURCE = 'field-boundary';
const VERTEX_SOURCE = 'field-vertices';
const SATELLITE_SOURCE = 'sentinel-overlay';

// Centre of India, zoomed out enough to see where you are before you zoom in.
const INITIAL_CENTER: LonLat = [78.9, 22.6];
const INITIAL_ZOOM = 4;

export interface FieldMapProps {
  ring: LonLat[];
  onChange: (ring: LonLat[]) => void;
  /** Sentinel-2 index overlay from /geo/indices. Null hides the layer. */
  tileUrlTemplate?: string | null;
  className?: string;
}

/**
 * Tap-to-draw field boundary on an OpenStreetMap basemap.
 *
 * Drawing is hand-rolled rather than pulled from a draw plugin: the plugins in
 * this space target mapbox-gl and the MapLibre forks are unmaintained enough to
 * be a poor bet the week before a demo. Tap-to-add-corner is the whole
 * interaction a farmer needs, and it is about eighty lines.
 */
export function FieldMap({ ring, onChange, tileUrlTemplate, className }: FieldMapProps) {
  const t = useTranslation();
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const [ready, setReady] = useState(false);
  const [locating, setLocating] = useState(false);

  // The click handler is registered once, so it must not close over stale ring
  // state. A ref keeps the latest value available without re-registering.
  const ringRef = useRef(ring);
  ringRef.current = ring;

  // ------------------------------------------------------------ init
  useEffect(() => {
    if (map.current || !container.current) return;

    const instance = new maplibregl.Map({
      container: container.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: 'raster',
            tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '© OpenStreetMap contributors',
          },
        },
        layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
      },
      center: INITIAL_CENTER,
      zoom: INITIAL_ZOOM,
      attributionControl: { compact: true },
    });

    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    instance.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');

    instance.on('load', () => {
      instance.addSource(DRAWN_SOURCE, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });
      instance.addSource(VERTEX_SOURCE, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      });

      instance.addLayer({
        id: 'field-fill',
        type: 'fill',
        source: DRAWN_SOURCE,
        paint: { 'fill-color': '#1f6b3b', 'fill-opacity': 0.25 },
      });
      instance.addLayer({
        id: 'field-outline',
        type: 'line',
        source: DRAWN_SOURCE,
        paint: { 'line-color': '#1f6b3b', 'line-width': 2.5 },
      });
      instance.addLayer({
        id: 'field-corners',
        type: 'circle',
        source: VERTEX_SOURCE,
        paint: {
          'circle-radius': 6,
          'circle-color': '#ffffff',
          'circle-stroke-color': '#1f6b3b',
          'circle-stroke-width': 2.5,
        },
      });

      setReady(true);
    });

    instance.on('click', (event) => {
      const next: LonLat[] = [...ringRef.current, [event.lngLat.lng, event.lngLat.lat]];
      onChange(next);
    });

    // A crosshair says "you can draw here" in a way no label does.
    instance.getCanvas().style.cursor = 'crosshair';
    map.current = instance;

    return () => {
      instance.remove();
      map.current = null;
    };
    // onChange is stable via useCallback in the parent; re-running would
    // destroy and rebuild the map on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ------------------------------------------------- redraw on ring change
  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready) return;

    const vertices = {
      type: 'FeatureCollection' as const,
      features: ring.map((position) => ({
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: position },
        properties: {},
      })),
    };
    (instance.getSource(VERTEX_SOURCE) as maplibregl.GeoJSONSource)?.setData(vertices);

    const polygon =
      ring.length >= 3
        ? {
            type: 'FeatureCollection' as const,
            features: [
              {
                type: 'Feature' as const,
                geometry: {
                  type: 'Polygon' as const,
                  coordinates: [closedRing(ring)],
                },
                properties: {},
              },
            ],
          }
        : { type: 'FeatureCollection' as const, features: [] };
    (instance.getSource(DRAWN_SOURCE) as maplibregl.GeoJSONSource)?.setData(polygon);
  }, [ring, ready]);

  // ------------------------------------------------- satellite overlay
  useEffect(() => {
    const instance = map.current;
    if (!instance || !ready) return;

    if (instance.getLayer('sentinel-layer')) instance.removeLayer('sentinel-layer');
    if (instance.getSource(SATELLITE_SOURCE)) instance.removeSource(SATELLITE_SOURCE);
    if (!tileUrlTemplate) return;

    instance.addSource(SATELLITE_SOURCE, {
      type: 'raster',
      tiles: [tileUrlTemplate],
      tileSize: 256,
      attribution: 'Copernicus Sentinel-2',
    });
    // Beneath the boundary so the farmer's own drawing stays legible on top.
    instance.addLayer({ id: 'sentinel-layer', type: 'raster', source: SATELLITE_SOURCE }, 'field-fill');
  }, [tileUrlTemplate, ready]);

  // ------------------------------------------------------------ actions
  const undo = useCallback(() => onChange(ring.slice(0, -1)), [ring, onChange]);
  const clear = useCallback(() => onChange([]), [onChange]);

  const locate = useCallback(() => {
    if (!('geolocation' in navigator)) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        map.current?.flyTo({
          center: [position.coords.longitude, position.coords.latitude],
          zoom: 16,
        });
        setLocating(false);
      },
      () => setLocating(false),
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }, []);

  const problem = ring.length >= 3 ? validateRing(ring) : null;
  // Suppress the readout when the ring is invalid: a self-intersecting boundary
  // produces a confident-looking number that means nothing.
  const area = ring.length >= 3 && problem === null ? polygonAreaHa(ring) : 0;

  return (
    <div className={className}>
      <div
        ref={container}
        className="h-[360px] w-full overflow-hidden rounded-lg border border-border"
        role="application"
        aria-label={t('map.aria')}
      />

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={locate} disabled={locating}>
          <Crosshair className="h-4 w-4" aria-hidden />
          {t('map.findMe')}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={undo}
          disabled={ring.length === 0}
        >
          <Undo2 className="h-4 w-4" aria-hidden />
          {t('map.undo')}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={clear} disabled={ring.length === 0}>
          <Trash2 className="h-4 w-4" aria-hidden />
          {t('map.clear')}
        </Button>

        <span className="ml-auto text-sm text-muted-foreground">
          {ring.length === 0
            ? t('map.hint')
            : ring.length < 3
              ? t('map.needMore', { count: 3 - ring.length })
              : problem !== null
                ? t('map.invalid')
                : t('map.area', { area: area.toFixed(2), corners: ring.length })}
        </span>
      </div>

      {problem && <p className="mt-2 text-sm text-destructive">{problem}</p>}
    </div>
  );
}
