/**
 * TypeScript mirror of docs/api-contract.md (FROZEN v1).
 *
 * Rules this file encodes, so the compiler enforces them:
 *  - Field naming is snake_case. Do not camelCase on the way in.
 *  - Coordinates are [longitude, latitude] (GeoJSON order), never [lat, lon].
 *  - Money is an integer number of rupees.
 *  - Any economics field may be null. `null` means "not available", never zero.
 *
 * If this file and api-contract.md disagree, the document wins and this file is a bug.
 */

// ---------------------------------------------------------------- primitives

/** Integer rupees. 42000 means Rs 42,000. */
export type Money = number;

/** ISO 8601 date, YYYY-MM-DD. */
export type IsoDate = string;

/** ISO 8601 UTC timestamp, 2026-08-16T12:30:00Z. */
export type IsoTimestamp = string;

/** GeoJSON order: [longitude, latitude]. */
export type LonLat = [number, number];

export type Season = 'kharif' | 'rabi' | 'zaid';
export type Irrigation = 'rainfed' | 'canal' | 'tubewell' | 'drip';
export type Confidence = 'high' | 'medium' | 'low';
export type Lang = 'en' | 'hi';

/** Contract section 3.4: `reasons[].factor` is a closed set. */
export const REASON_FACTORS = [
  'soil_ph',
  'soil_texture',
  'nitrogen',
  'rainfall',
  'temperature',
  'irrigation',
  'market_price',
  'season_fit',
  'rotation',
] as const;
export type ReasonFactor = (typeof REASON_FACTORS)[number];

export type ReasonImpact = 'positive' | 'neutral' | 'negative';

// ----------------------------------------------------------------- location

export interface PointLocation {
  type: 'point';
  lat: number;
  lon: number;
}

export interface AdminLocation {
  type: 'admin';
  state_code: string;
  district_code: string;
}

export interface PolygonGeometry {
  type: 'Polygon';
  /** First ring only, closed (first point === last point), max 200 vertices. */
  coordinates: LonLat[][];
}

export interface PolygonLocation {
  type: 'polygon';
  geometry: PolygonGeometry;
}

/** Tagged union, discriminated by `type`. Exactly one form. */
export type Location = PointLocation | AdminLocation | PolygonLocation;

// -------------------------------------------------------------------- errors

export type ApiErrorCode =
  | 'VALIDATION_ERROR'
  | 'INVALID_LOCATION'
  | 'UNSUPPORTED_SEASON'
  | 'NOT_FOUND'
  | 'NO_DATA_FOR_LOCATION'
  | 'RATE_LIMITED'
  | 'UPSTREAM_FAILED'
  | 'INTERNAL_ERROR';

export interface ApiErrorBody {
  code: ApiErrorCode | string;
  message: string;
  field?: string;
  request_id?: string;
}

/** Every non-2xx response uses this shape. No exceptions. */
export interface ApiErrorEnvelope {
  error: ApiErrorBody;
}

// ---------------------------------------------------------------- meta 3.2/3.3

export interface District {
  district_code: string;
  district_name: string;
  centroid: LonLat;
}

export interface State {
  state_code: string;
  state_name: string;
  districts: District[];
}

export interface DistrictsResponse {
  states: State[];
}

export interface Crop {
  crop_code: string;
  name: string;
  name_hi?: string;
  category: string;
  seasons: Season[];
}

export interface CropsResponse {
  crops: Crop[];
}

// ------------------------------------------------------------- conditions 3.4

export interface SoilConditions {
  texture: string | null;
  ph: number | null;
  organic_carbon_pct: number | null;
  nitrogen_kg_ha: number | null;
  phosphorus_kg_ha: number | null;
  potassium_kg_ha: number | null;
  source: string | null;
}

export interface WeatherConditions {
  annual_rainfall_mm: number | null;
  season_rainfall_mm: number | null;
  avg_temp_c: number | null;
  source: string | null;
}

export interface Conditions {
  soil: SoilConditions;
  weather: WeatherConditions;
  ndvi_current: number | null;
  /** 0..1. Drives `confidence`. */
  data_completeness: number;
}

export interface ResolvedLocation {
  state_code: string;
  district_code: string;
  district_name: string;
  centroid: LonLat;
  area_ha: number;
}

// -------------------------------------------------------- recommendations 3.4

export interface Constraints {
  exclude_crops?: string[];
  /** Per hectare. */
  max_input_cost?: Money;
  organic_only?: boolean;
}

/** Values from a farmer's Soil Health Card. Every field independently optional. */
export interface SoilTest {
  nitrogen_kg_ha: number | null;
  phosphorus_kg_ha: number | null;
  potassium_kg_ha: number | null;
}

export interface RecommendationRequest {
  location: Location;
  season: Season;
  /** > 0, <= 100. */
  area_ha: number;
  sowing_date?: IsoDate;
  irrigation?: Irrigation;
  /** Overrides sampled soil values — a lab result for this field beats a model. */
  soil_test?: SoilTest;
  constraints?: Constraints;
  /** 1..10, default 5. */
  limit?: number;
}

export interface Reason {
  factor: ReasonFactor | string;
  impact: ReasonImpact;
  detail: string;
}

export interface DateWindow {
  start: IsoDate;
  end: IsoDate;
}

export interface CropCalendar {
  sowing_window: DateWindow;
  harvest_window: DateWindow;
  duration_days: number;
}

/**
 * Whole-plot figures except the `*_per_ha` fields.
 * Never recompute these on the client - see api-contract.md section 4.
 */
export interface Economics {
  expected_yield_t_ha: number | null;
  input_cost_per_ha: Money | null;
  expected_price_per_quintal: Money | null;
  gross_revenue: Money | null;
  net_margin: Money | null;
  margin_per_ha: Money | null;
  price_source: string | null;
  price_as_of: IsoDate | null;
}

export type RiskSeverity = 'low' | 'medium' | 'high';

export interface Risk {
  type: string;
  name: string;
  severity: RiskSeverity | string;
}

export interface Recommendation {
  /** 1-based, ascending, always <= request limit. */
  rank: number;
  crop_code: string;
  name: string;
  variety_suggested: string | null;
  /** 0..1, relative within this response only. Never compare across requests. */
  score: number;
  confidence: Confidence;
  /** 2-4 entries. */
  reasons: Reason[];
  calendar: CropCalendar;
  economics: Economics;
  risks: Risk[];
}

export interface Warning {
  code: string;
  message: string;
}

export interface RecommendationResponse {
  request_id: string;
  generated_at: IsoTimestamp;
  location_resolved: ResolvedLocation;
  conditions: Conditions;
  recommendations: Recommendation[];
  /** May be empty, but always present. */
  warnings: Warning[];
}

// ---------------------------------------------------------- field summary 3.6

export interface FieldSummaryRequest {
  location: Location;
}

export interface FieldSummaryResponse {
  location_resolved: ResolvedLocation;
  conditions: Conditions;
}

// ---------------------------------------------------------------- prices 3.7

export interface PricePoint {
  date: IsoDate;
  modal_price: Money;
  min_price: Money;
  max_price: Money;
  mandi: string;
}

export interface PricesResponse {
  crop_code: string;
  unit: 'per_quintal' | string;
  series: PricePoint[];
  source: string;
  fetched_at: IsoTimestamp;
}

// ---------------------------------------------------------------- health 3.1

// ------------------------------------------- spectral indices (additive)

export interface SpectralIndex {
  key: string;
  name: string;
  value: number | null;
  range_min: number;
  range_max: number;
  interpretation: string;
  formula: string;
}

export interface NdviHistoryPoint {
  date: IsoDate;
  ndvi: number | null;
}

export interface IndicesRequest {
  location: Location;
}

export interface IndicesResponse {
  location_resolved: ResolvedLocation;
  observed_on: IsoDate | null;
  cloud_cover_pct: number | null;
  indices: SpectralIndex[];
  history: NdviHistoryPoint[];
  source: string;
  /** Sentinel-2 overlay tiles; null when Earth Engine is not configured. */
  tile_url_template: string | null;
}

export interface HealthResponse {
  status: string;
  version: string;
  geo_service: string;
  db: string;
}
