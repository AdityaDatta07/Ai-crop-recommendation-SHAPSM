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
  /** Kept because the frozen v1 contract exposes it. New languages use `names`. */
  name_hi?: string;
  /** Locale code -> crop name, for every language the API speaks. */
  names?: Record<string, string>;
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

/** Where the satellite looked. `precision` says how precisely. */
export interface ResolvedLocation {
  state_code: string;
  district_code: string;
  district_name: string;
  centroid: LonLat;
  area_ha: number;
  area_acres?: number | null;
  /**
   * "district" means the reading is of the district centroid — generally its
   * main town — and not of the farmer's field. The UI must say so.
   */
  precision?: 'field' | 'point' | 'district';
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
  /** Crop code grown here last season, for the side-by-side comparison. */
  previous_crop?: string;
  constraints?: Constraints;
  /** 1..10, default 5. */
  limit?: number;
}

export interface Reason {
  factor: ReasonFactor | string;
  impact: ReasonImpact;
  /** English, from the server. The fallback when `code` has no translation. */
  detail: string;
  /** Which message this is. Render via renderServerText, not directly. */
  code?: string;
  params?: Record<string, unknown>;
}

export interface DateWindow {
  start: IsoDate;
  end: IsoDate;
}

export interface CropCalendar {
  sowing_window: DateWindow;
  harvest_window: DateWindow;
  duration_days: number;
  days_until_sowing?: number | null;
  /** Whether this season's sowing window is still open. */
  window_status?: 'open' | 'upcoming' | 'closed_this_year' | null;
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
  /** Same money in acres. Computed server-side — the client never converts. */
  input_cost_per_acre?: number | null;
  margin_per_acre?: number | null;
  expected_yield_t_acre?: number | null;
}

export type RiskSeverity = 'low' | 'medium' | 'high';

/** Projected price for the month the crop is actually sold. */
export interface PriceOutlook {
  harvest_month: string | null;
  expected_per_quintal: number | null;
  low_per_quintal: number | null;
  high_per_quintal: number | null;
  msp_floor_per_quintal: number | null;
  current_per_quintal: number | null;
  /** How the figure was reached. Render each differently — they are different claims. */
  basis: 'seasonal_history' | 'msp_floor' | 'current_only' | 'none';
  observations_used: number;
  explanation: string;
  explanation_code?: string;
  explanation_params?: Record<string, unknown>;
  /** How far today's market price sits below MSP, when it does. */
  below_msp_by?: number | null;
}

/** One factor's exact share of the score. Contributions sum to the score. */
export interface Attribution {
  factor: string;
  contribution: number;
  headroom: number;
  score: number;
  impact: 'positive' | 'neutral' | 'negative';
  detail: string;
  /** Shares the ranker's reason codes. Render via renderServerText('reason', …). */
  code?: string;
  params?: Record<string, unknown>;
}

/** What would have to change for this crop to rank higher. */
export interface Counterfactual {
  factor: string;
  /** threshold = a reachable change; limiting = nothing reachable helps. */
  kind: 'threshold' | 'fragility' | 'limiting';
  current_value: string;
  target_value: string | null;
  score_gain: number;
  rank_gain: number;
  /** English, from the server. The fallback when there is no translation. */
  message: string;
  params?: Record<string, unknown>;
}

export interface Risk {
  type: string;
  name: string;
  severity: RiskSeverity | string;
}

/** How a crop sits against what grew here last season. */
export interface RotationNote {
  score: number;
  code: string;
  params?: Record<string, unknown>;
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
  /** Position if ordered by money instead of fit. Null when unpriced. */
  rank_by_return?: number | null;
  /** Present only when the farmer named last season's crop. */
  rotation?: RotationNote | null;
  calendar: CropCalendar;
  economics: Economics;
  /**
   * Added after the v1 freeze, so optional on read: a result cached before this
   * shipped will not have it, and the UI must not break on those.
   */
  price_outlook?: PriceOutlook | null;
  attribution?: Attribution[];
  counterfactuals?: Counterfactual[];
  risks: Risk[];
}

export interface Warning {
  code: string;
  /** English, from the server. The fallback when `code` has no translation. */
  message: string;
  params?: Record<string, unknown>;
}

/** One crop valued on this field, for a like-for-like comparison. */
export interface ComparisonSide {
  crop_code: string;
  name: string;
  rank: number | null;
  score: number | null;
  net_margin: number | null;
  margin_per_ha: number | null;
  margin_per_acre: number | null;
  expected_yield_t_ha: number | null;
}

export interface CropComparison {
  previous: ComparisonSide;
  recommended: ComparisonSide;
  margin_difference: number | null;
  rank_difference: number | null;
  same_crop: boolean;
  verdict: string;
  verdict_code?: string;
  verdict_params?: Record<string, unknown>;
}

export type Level = 'low' | 'medium' | 'high';

export type WaterStatus =
  | 'rain_sufficient'
  | 'needs_irrigation'
  | 'cannot_meet'
  | 'surplus'
  | 'unknown';

export interface WaterBudget {
  crop_code: string;
  name: string;
  requirement_mm: number;
  comfortable_mm: number;
  /** A THIRTY-YEAR NORMAL, not a forecast. The UI must say so. */
  season_rainfall_mm: number | null;
  /** What the crop can use after runoff and percolation. Always < what fell. */
  effective_rainfall_mm: number | null;
  deficit_mm: number | null;
  deficit_m3: number | null;
  /** To reach the MINIMUM of the crop's band, not a comfortable level. */
  waterings: number | null;
  waterings_comfortable: number | null;
  deficit_comfortable_mm: number | null;
  surplus_mm: number | null;
  status: WaterStatus;
  can_be_met: boolean;
}

export interface RiskExposure {
  crop_code: string;
  name: string;
  agronomic: Level;
  price: Level;
  water: Level;
  risk_types: string[];
  /** High-severity risks by name, so the UI can say "pod borer". */
  severe_risks: string[];
  /** Message codes naming what drives the exposure. */
  drivers: string[];
}

export interface Allocation {
  crop_code: string;
  name: string;
  /** 0..1 of the field. */
  share: number;
  area_ha: number;
  net_margin: Money | null;
}

export interface RiskPlan {
  exposures: RiskExposure[];
  /** Empty when splitting would not help. `verdict_code` says why. */
  plan: Allocation[];
  /** 0 = the two crops fail for unrelated reasons, 1 = they fail together. */
  overlap: number | null;
  combined_margin: Money | null;
  /** The best a SINGLE crop could earn here — by money, not by rank. */
  single_crop_margin: Money | null;
  single_crop_name: string;
  single_crop_code: string;
  /** What the split costs against a single crop. Negative when it earns more. */
  margin_given_up: Money | null;
  verdict_code: string;
  verdict_params?: Record<string, unknown>;
}

/** The inputs an answer was computed from. Lets a saved link be recalculated. */
export interface RequestEcho {
  location: Location;
  season: Season;
  area_ha: number;
  irrigation?: Irrigation | null;
  soil_test?: SoilTest | null;
  previous_crop?: string | null;
}

/**
 * How often THIS TOOL ranked a crop first here. Read the names literally.
 *
 * `advisories_total` counts advisories this application issued. It is not a
 * count of farmers, plots or sowing intentions — we have no visibility of
 * those, and no public feed publishes them at district level in time to act
 * on. Any UI wording that implies otherwise is a bug; see
 * apps/api/tests/test_crowding.py, which fails on those words appearing.
 *
 * `share` is null below the minimum sample, and then there is no percentage
 * at all rather than a hedged one.
 */
export interface AdviceConcentration {
  crop_code: string;
  times_ranked_first: number;
  advisories_total: number;
  share: number | null;
  band: 'crowded' | 'common' | 'uncommon' | 'never' | 'unknown';
  code?: string;
  params?: Record<string, unknown>;
}

/**
 * What the crop fetched in its harvest month against the rest of the year.
 *
 * Backward-looking by construction. `scope` says whose market: "district" is
 * the local record, "national" means the district had too little history and
 * every district is pooled — useful, but a different claim, and the UI must
 * distinguish them.
 */
export interface HarvestDip {
  crop_code: string;
  harvest_month: number | null;
  harvest_median: number | null;
  other_median: number | null;
  dip_fraction: number | null;
  band: 'steep' | 'mild' | 'none' | 'unknown';
  observations: number;
  scope: 'district' | 'national' | 'none';
  code?: string;
  params?: Record<string, unknown>;
}

export interface Crowding {
  crop_code: string;
  name: string;
  concentration: AdviceConcentration;
  dip: HarvestDip;
  caveat_codes: string[];
  /** How many of `advisories_total` came from scripts/seed_advisories.py. */
  seeded_advisories?: number;
}

/**
 * `source` is the honesty dial. The UI must render each value differently —
 * see components/recommendation/chat-box.tsx for why.
 */
/** Static reference table. See data/reference/msp.yaml. */
export interface MspCrop {
  name: string;
  name_hi?: string;
  group: string;
  season: string;
  /** Null when the government notifies an MSP for a crop this app does not rank. */
  crop_code: string | null;
  msp_per_quintal: number;
  /** Null for grades whose cost is not compiled separately. */
  cost_a2fl_per_quintal: number | null;
}

export interface MspSource {
  key: string;
  title: string;
  publisher: string;
  published: string;
  url: string;
}

export interface MspResponse {
  marketing_season: string;
  updated: string;
  crops: MspCrop[];
  sources: Record<string, MspSource>;
  not_listed_here: { name: string; name_hi?: string; note?: string }[];
}

export interface ChatResponse {
  source: 'refusal' | 'template' | 'model' | 'unavailable';
  code?: string;
  params?: Record<string, unknown>;
  /** Free prose. Only ever present when source is "model". */
  text?: string;
  refusal_category?: string | null;
}

export interface RecommendationResponse {
  request_id: string;
  generated_at: IsoTimestamp;
  location_resolved: ResolvedLocation;
  conditions: Conditions;
  recommendations: Recommendation[];
  comparison?: CropComparison | null;
  /** May be empty, but always present. */
  warnings: Warning[];
  /** Absent on results saved before this field existed. */
  request_echo?: RequestEcho | null;
  /** Exposure, and whether splitting the field helps. */
  risk?: RiskPlan | null;
  /** Water need against rainfall, per crop. */
  water?: WaterBudget[];
  /** District crowding, per crop. Counts of our own advice, never of farmers. */
  crowding?: Crowding[];
}

// ---------------------------------------------------------- field summary 3.6

export interface FieldSummaryRequest {
  location: Location;
}

export interface FieldSummaryResponse {
  location_resolved: ResolvedLocation;
  conditions: Conditions;
  /**
   * Set by the CLIENT, never the server, when the live call could not be
   * reached and a recording was served instead. See lib/offline.ts.
   */
  offline_recording?: boolean;
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

export interface CropCycle {
  peak_month: string;
  peak_ndvi: number;
  season: Season;
  start_month: string;
  end_month: string;
  months: number;
}

/**
 * Cropping intensity and season timing from NDVI. NOT crop identification.
 * The error runs one way: cloud hides crops, so intensity can be understated
 * and never overstated.
 */
export interface CropHistory {
  intensity: 'single' | 'double' | 'triple' | 'fallow' | 'uncropped' | 'unknown';
  cycles: CropCycle[];
  cycles_per_year: number;
  seasons_used: string[];
  fallow_months: number;
  observed_months: number;
  total_months: number;
  season_coverage: Record<string, number>;
  confidence: Level;
  caveat_codes: string[];
}

/**
 * Growing vigour against surrounding farmland. NOT a yield, and not a
 * judgement of the farmer — the neighbours may grow a different crop.
 */
export interface Productivity {
  plot_amplitude: number | null;
  percentile: number | null;
  band: 'well_above' | 'above' | 'typical' | 'below' | 'well_below' | 'unknown';
  percentiles: Record<string, number>;
  neighbourhood_km: number;
  sample_pixels: number;
  caveat_codes: string[];
}

export interface IndicesResponse {
  location_resolved: ResolvedLocation;
  observed_on: IsoDate | null;
  cloud_cover_pct: number | null;
  indices: SpectralIndex[];
  history: NdviHistoryPoint[];
  crop_history?: CropHistory | null;
  productivity?: Productivity | null;
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
