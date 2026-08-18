import type { LonLat } from '@/types/api';

/**
 * Geometry helpers for the map, used ONLY for live feedback while drawing.
 *
 * The server recomputes area authoritatively in services/geo/districts.py and
 * that is the number that reaches the recommendation. This exists so the farmer
 * can see the plot growing as they tap, not to produce a figure anyone acts on.
 * If these two ever disagree, the server is right.
 */

const METRES_PER_DEGREE_LAT = 111_320;

/** Shoelace on an equirectangular projection about the ring's own centroid. */
export function polygonAreaHa(ring: LonLat[]): number {
  const points = closedRing(ring).slice(0, -1);
  if (points.length < 3) return 0;

  const meanLat = points.reduce((sum, p) => sum + p[1], 0) / points.length;
  const metresPerDegreeLon = METRES_PER_DEGREE_LAT * Math.cos((meanLat * Math.PI) / 180);

  const projected = points.map(([lon, lat]): [number, number] => [
    lon * metresPerDegreeLon,
    lat * METRES_PER_DEGREE_LAT,
  ]);

  let total = 0;
  for (let i = 0; i < projected.length; i += 1) {
    const [x1, y1] = projected[i];
    const [x2, y2] = projected[(i + 1) % projected.length];
    total += x1 * y2 - x2 * y1;
  }

  return Math.abs(total) / 2 / 10_000;
}

/** GeoJSON requires the first and last position to be identical. */
export function closedRing(ring: LonLat[]): LonLat[] {
  if (ring.length < 3) return ring;
  const [first] = ring;
  const last = ring[ring.length - 1];
  return first[0] === last[0] && first[1] === last[1] ? ring : [...ring, first];
}

export function centroid(ring: LonLat[]): LonLat {
  const points = closedRing(ring).slice(0, -1);
  const lon = points.reduce((sum, p) => sum + p[0], 0) / points.length;
  const lat = points.reduce((sum, p) => sum + p[1], 0) / points.length;
  return [lon, lat];
}

/** Contract limits: max 200 vertices, max 100 ha. */
export const MAX_VERTICES = 200;
export const MAX_AREA_HA = 100;

/** Proper segment intersection, excluding shared endpoints. */
function segmentsCross(a1: LonLat, a2: LonLat, b1: LonLat, b2: LonLat): boolean {
  const orient = (p: LonLat, q: LonLat, r: LonLat) =>
    (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]);

  const d1 = orient(b1, b2, a1);
  const d2 = orient(b1, b2, a2);
  const d3 = orient(a1, a2, b1);
  const d4 = orient(a1, a2, b2);
  return d1 > 0 !== d2 > 0 && d3 > 0 !== d4 > 0;
}

/**
 * Does the boundary cross itself?
 *
 * polygonAreaHa uses a signed shoelace sum, so a self-intersecting ring reports
 * a meaningless area — the lobes cancel. Tapping corners out of order on a
 * phone produces exactly that, and without this check the farmer sees a
 * confident number that is simply wrong. The server enforces the same rule.
 */
export function isSelfIntersecting(ring: LonLat[]): boolean {
  const points = closedRing(ring).slice(0, -1);
  const count = points.length;
  if (count < 4) return false;

  const edges: [LonLat, LonLat][] = points.map((point, i) => [point, points[(i + 1) % count]]);

  for (let i = 0; i < count; i += 1) {
    // Skip adjacent edges: they share a vertex by construction.
    for (let j = i + 2; j < count; j += 1) {
      if (i === 0 && j === count - 1) continue;
      if (segmentsCross(edges[i][0], edges[i][1], edges[j][0], edges[j][1])) return true;
    }
  }
  return false;
}

export function validateRing(ring: LonLat[]): string | null {
  if (ring.length < 3) return 'A field needs at least three corners.';
  if (ring.length > MAX_VERTICES) return `A field may have at most ${MAX_VERTICES} corners.`;
  if (isSelfIntersecting(ring)) {
    return 'The boundary crosses itself. Undo the last corners and redraw without overlapping.';
  }
  const area = polygonAreaHa(ring);
  if (area > MAX_AREA_HA) {
    return `That field is about ${area.toFixed(1)} ha, over the ${MAX_AREA_HA} ha limit.`;
  }
  return null;
}
