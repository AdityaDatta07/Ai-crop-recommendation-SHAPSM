# API Contract

**Status:** FROZEN as of v1. Breaking changes require a team-wide announcement and a version bump.

Base URL (dev): `http://localhost:8000`
Base URL (prod): set via `NEXT_PUBLIC_API_BASE_URL`
All paths are prefixed `/api/v1`.

---

## 1. Conventions

| Rule | Value |
|---|---|
| Content type | `application/json; charset=utf-8` |
| Field naming | `snake_case` |
| Dates | ISO 8601 date `YYYY-MM-DD` |
| Timestamps | ISO 8601 UTC, `2026-08-16T12:30:00Z` |
| Currency | INR, integer rupees (no paise, no formatting) |
| Area | hectares, float |
| Yield | tonnes per hectare, float |
| Coordinates | WGS84, `[longitude, latitude]` order (GeoJSON standard) |
| Language | `lang` query param, ISO 639-1. Default `en`. Supported: `en`, `hi` |
| Auth | None in v1. All endpoints public. |

Unknown request fields are ignored, not rejected. Clients must ignore unknown response fields — this lets us add fields without breaking anyone.

---

## 2. Shared objects

### 2.1 `Location`

A tagged union. Exactly one form, discriminated by `type`.

```jsonc
// (a) Map pin
{ "type": "point", "lat": 26.8467, "lon": 80.9462 }

// (b) Administrative area
{ "type": "admin", "state_code": "UP", "district_code": "UP-LKO" }

// (c) Drawn field boundary — GeoJSON Polygon, first ring only, closed
{
  "type": "polygon",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[80.94,26.84],[80.95,26.84],[80.95,26.85],[80.94,26.85],[80.94,26.84]]]
  }
}
```

Constraints:
- `lat` −90..90, `lon` −180..180.
- Polygon: max 200 vertices, max area 100 ha, must be closed (first == last point).
- `state_code` / `district_code` must exist in `GET /meta/districts`.

### 2.2 `Money`

Plain integer rupees. Example: `42000` means ₹42,000.

### 2.3 Error envelope

Every non-2xx response uses this shape. No exceptions.

```json
{
  "error": {
    "code": "INVALID_LOCATION",
    "message": "Polygon area exceeds 100 ha limit.",
    "field": "location.geometry",
    "request_id": "req_01J8XA9"
  }
}
```

| HTTP | `code` values |
|---|---|
| 400 | `VALIDATION_ERROR`, `INVALID_LOCATION`, `UNSUPPORTED_SEASON` |
| 404 | `NOT_FOUND` |
| 422 | `NO_DATA_FOR_LOCATION` |
| 429 | `RATE_LIMITED` |
| 502 | `UPSTREAM_FAILED` (Earth Engine / market API down) |
| 500 | `INTERNAL_ERROR` |

`request_id` is echoed in the `X-Request-Id` response header on all responses. Always log it.

---

## 3. Endpoints

### 3.1 `GET /health`

Liveness probe. Not versioned, no `/api/v1` prefix.

**200**
```json
{ "status": "ok", "version": "1.0.0", "geo_service": "ok", "db": "ok" }
```

---

### 3.2 `GET /api/v1/meta/districts`

Reference list for the state/district dropdowns. Cache aggressively client-side.

Query: `state_code` (optional) — filter to one state.

**200**
```json
{
  "states": [
    {
      "state_code": "UP",
      "state_name": "Uttar Pradesh",
      "districts": [
        { "district_code": "UP-LKO", "district_name": "Lucknow", "centroid": [80.94, 26.84] }
      ]
    }
  ]
}
```

---

### 3.3 `GET /api/v1/meta/crops`

Master crop list. Used to render filters and to resolve `crop_code`.

**200**
```json
{
  "crops": [
    {
      "crop_code": "WHEAT",
      "name": "Wheat",
      "name_hi": "गेहूँ",
      "category": "cereal",
      "seasons": ["rabi"]
    }
  ]
}
```

`crop_code` is the stable join key across the whole system. Never display it; never change it.

---

### 3.4 `POST /api/v1/recommendations` — core endpoint

**Request**

```json
{
  "location": { "type": "point", "lat": 26.8467, "lon": 80.9462 },
  "season": "rabi",
  "area_ha": 1.5,
  "sowing_date": "2026-11-15",
  "irrigation": "canal",
  "constraints": {
    "exclude_crops": ["SUGARCANE"],
    "max_input_cost": 60000,
    "organic_only": false
  },
  "limit": 5
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `location` | `Location` | yes | See 2.1 |
| `season` | enum | yes | `kharif` \| `rabi` \| `zaid` |
| `area_ha` | float | yes | > 0, ≤ 100 |
| `sowing_date` | date | no | Defaults to season start for the district |
| `irrigation` | enum | no | `rainfed` \| `canal` \| `tubewell` \| `drip`. Default `rainfed` |
| `constraints.exclude_crops` | string[] | no | `crop_code` values |
| `constraints.max_input_cost` | Money | no | Per hectare |
| `constraints.organic_only` | bool | no | Default `false` |
| `limit` | int | no | 1–10, default 5 |

**200**

```json
{
  "request_id": "req_01J8XA9",
  "generated_at": "2026-08-16T12:30:00Z",
  "location_resolved": {
    "state_code": "UP",
    "district_code": "UP-LKO",
    "district_name": "Lucknow",
    "centroid": [80.94, 26.84],
    "area_ha": 1.5
  },
  "conditions": {
    "soil": {
      "texture": "loam",
      "ph": 7.2,
      "organic_carbon_pct": 0.54,
      "nitrogen_kg_ha": 240,
      "phosphorus_kg_ha": 18,
      "potassium_kg_ha": 190,
      "source": "SoilGrids250m + Soil Health Card"
    },
    "weather": {
      "annual_rainfall_mm": 940,
      "season_rainfall_mm": 110,
      "avg_temp_c": 22.4,
      "source": "IMD gridded 1991-2020 normals"
    },
    "ndvi_current": 0.42,
    "data_completeness": 0.92
  },
  "recommendations": [
    {
      "rank": 1,
      "crop_code": "WHEAT",
      "name": "Wheat",
      "variety_suggested": "HD-3086",
      "score": 0.87,
      "confidence": "high",
      "reasons": [
        { "factor": "soil_ph", "impact": "positive", "detail": "pH 7.2 is within wheat's optimal 6.0-7.5" },
        { "factor": "rainfall", "impact": "neutral", "detail": "Requires 2-3 supplemental irrigations" }
      ],
      "calendar": {
        "sowing_window": { "start": "2026-11-05", "end": "2026-12-10" },
        "harvest_window": { "start": "2027-03-25", "end": "2027-04-20" },
        "duration_days": 135
      },
      "economics": {
        "expected_yield_t_ha": 4.2,
        "input_cost_per_ha": 38500,
        "expected_price_per_quintal": 2400,
        "gross_revenue": 151200,
        "net_margin": 93450,
        "margin_per_ha": 62300,
        "price_source": "Agmarknet, Lucknow mandi, 90-day avg",
        "price_as_of": "2026-08-10"
      },
      "risks": [
        { "type": "pest", "name": "Yellow rust", "severity": "medium" }
      ]
    }
  ],
  "warnings": [
    { "code": "STALE_PRICE_DATA", "message": "Market prices are 6 days old." }
  ]
}
```

Response rules:
- `recommendations` is sorted by `rank` ascending, `rank` starts at 1, always ≤ `limit`.
- `score` is 0.0–1.0. It is **relative within this response only** — do not compare scores across requests.
- `confidence` is `high` | `medium` | `low`, derived from `data_completeness`.
- Economics fields are computed for the **whole plot** (`area_ha`), except `*_per_ha` fields.
- `reasons` has 2–4 entries. `factor` values are a closed set: `soil_ph`, `soil_texture`, `nitrogen`, `rainfall`, `temperature`, `irrigation`, `market_price`, `season_fit`, `rotation`.
- `warnings` may be empty `[]` but is always present.
- Any economics field may be `null` if the source data is unavailable. Frontend must render `—` for null, not `0`.

**Errors:** `400 VALIDATION_ERROR`, `400 INVALID_LOCATION`, `422 NO_DATA_FOR_LOCATION`, `502 UPSTREAM_FAILED`.

**Timing:** target p95 under 4s. If Earth Engine is cold this can reach 15s — frontend must show a progress state and use a 30s client timeout.

---

### 3.5 `GET /api/v1/recommendations/{request_id}`

Re-fetch a previous result. Enables shareable links and offline replay. Results retained 30 days.

**200** — identical body to 3.4.
**404** `NOT_FOUND` if expired or unknown.

---

### 3.6 `POST /api/v1/geo/field-summary`

Conditions only, no ranking. Used by the map screen to show soil/weather as soon as a pin is dropped, before the farmer commits to a full recommendation.

**Request**
```json
{ "location": { "type": "point", "lat": 26.8467, "lon": 80.9462 } }
```

**200** — returns the `conditions` and `location_resolved` objects from 3.4, nothing else.

**Timing:** target p95 under 2s.

---

### 3.7 `GET /api/v1/prices/{crop_code}`

Recent mandi prices for one crop.

Query: `district_code` (optional), `days` (optional, default 90, max 365).

**200**
```json
{
  "crop_code": "WHEAT",
  "unit": "per_quintal",
  "series": [
    { "date": "2026-08-10", "modal_price": 2400, "min_price": 2280, "max_price": 2510, "mandi": "Lucknow" }
  ],
  "source": "Agmarknet",
  "fetched_at": "2026-08-16T06:00:00Z"
}
```

---

## 4. Frontend rules

- Never compute economics client-side. Display what the API returns.
- Never hardcode a crop name. Resolve via `crop_code` against `/meta/crops`.
- Cache `/meta/*` in IndexedDB for offline use; they change rarely.
- Cache the last successful `/recommendations` response for offline replay.
- Treat any `null` economics field as "not available", never as zero.

## 5. Backend rules

- Return the full response shape even when partially degraded — fill unavailable fields with `null` and add a `warnings` entry.
- Never return a bare string or array at the top level. Always an object.
- Set `X-Request-Id` on every response.
- Validate with Pydantic models that mirror this document exactly.

---

## 6. Mocking

Before the backend exists, the frontend builds against fixtures in `data/seed/api-fixtures/`:

```
data/seed/api-fixtures/
├── recommendations.success.json
├── recommendations.low-confidence.json
├── recommendations.error-no-data.json
├── meta.districts.json
├── meta.crops.json
└── geo.field-summary.json
```

Set `USE_MOCK_GEO=true` to have the API serve these instead of calling Earth Engine.

---

## 7. Changelog

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-16 | Initial frozen contract |
