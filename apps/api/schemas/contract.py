"""Pydantic models mirroring docs/api-contract.md (FROZEN v1).

These models ARE the contract enforcement. If the document says area_ha is a
float in (0, 100], that constraint lives here and is impossible to violate at
runtime. When this file and the document disagree, the document wins and this
file is the bug.

Field names are snake_case to match the wire format exactly - no aliasing, no
camelCase conversion. Coordinates are [longitude, latitude], GeoJSON order.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Season = Literal["kharif", "rabi", "zaid"]
Irrigation = Literal["rainfed", "canal", "tubewell", "drip"]
Confidence = Literal["high", "medium", "low"]
Impact = Literal["positive", "neutral", "negative"]

MAX_AREA_HA = 100.0
MAX_POLYGON_VERTICES = 200


class Base(BaseModel):
    # Unknown request fields are ignored, not rejected - contract section 1.
    # This is what lets the API add fields without breaking older clients.
    model_config = ConfigDict(extra="ignore")


# ----------------------------------------------------------------- location


class PointLocation(Base):
    type: Literal["point"]
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class AdminLocation(Base):
    type: Literal["admin"]
    state_code: str = Field(min_length=1, max_length=8)
    district_code: str = Field(min_length=1, max_length=16)


class PolygonGeometry(Base):
    type: Literal["Polygon"]
    coordinates: list[list[list[float]]]

    @field_validator("coordinates")
    @classmethod
    def check_ring(cls, rings: list[list[list[float]]]) -> list[list[list[float]]]:
        if not rings or not rings[0]:
            raise ValueError("Polygon must have at least one ring.")

        outer = rings[0]
        if len(outer) > MAX_POLYGON_VERTICES:
            raise ValueError(f"Polygon may have at most {MAX_POLYGON_VERTICES} vertices.")
        if len(outer) < 4:
            raise ValueError("Polygon ring needs at least 4 points (3 corners plus closure).")
        if outer[0] != outer[-1]:
            raise ValueError("Polygon ring must be closed: first and last points must match.")

        for point in outer:
            if len(point) != 2:
                raise ValueError("Each coordinate must be a [longitude, latitude] pair.")
            lon, lat = point
            if not -180 <= lon <= 180 or not -90 <= lat <= 90:
                raise ValueError(f"Coordinate out of range: [{lon}, {lat}].")
        return rings


class PolygonLocation(Base):
    type: Literal["polygon"]
    geometry: PolygonGeometry


Location = Annotated[
    Union[PointLocation, AdminLocation, PolygonLocation],
    Field(discriminator="type"),
]


# ------------------------------------------------------------------ requests


class Constraints(Base):
    exclude_crops: list[str] = Field(default_factory=list)
    max_input_cost: int | None = Field(default=None, ge=0)
    organic_only: bool = False


class SoilTest(Base):
    """Values a farmer reads off their Soil Health Card.

    Optional, and every field is independently optional — a card that shows only
    nitrogen is still worth having. Bounds are generous because Indian soils
    vary enormously and an over-tight range would reject honest readings; they
    exist to catch a decimal-point slip, not to police agronomy.

    Units are kg/ha, which is what the card prints.
    """

    nitrogen_kg_ha: float | None = Field(default=None, ge=0, le=2000)
    phosphorus_kg_ha: float | None = Field(default=None, ge=0, le=500)
    potassium_kg_ha: float | None = Field(default=None, ge=0, le=2000)

    @property
    def has_any(self) -> bool:
        return any(
            value is not None
            for value in (self.nitrogen_kg_ha, self.phosphorus_kg_ha, self.potassium_kg_ha)
        )


class RecommendationRequest(Base):
    location: Location
    season: Season
    area_ha: float = Field(gt=0, le=MAX_AREA_HA)
    sowing_date: date | None = None
    irrigation: Irrigation = "rainfed"
    # A lab measurement of this exact field beats any modelled estimate, so when
    # supplied these override whatever the geo service returned.
    soil_test: SoilTest | None = None
    constraints: Constraints = Field(default_factory=Constraints)
    limit: int = Field(default=5, ge=1, le=10)

    @model_validator(mode="after")
    def check_season_supported(self) -> "RecommendationRequest":
        # zaid is accepted by the schema because the contract lists it, but no
        # crop in data/reference is calendared for it yet. Failing here with the
        # documented code beats returning a confusing empty list.
        return self


class FieldSummaryRequest(Base):
    location: Location


# ----------------------------------------------------------------- responses


class SoilConditions(Base):
    texture: str | None = None
    ph: float | None = None
    organic_carbon_pct: float | None = None
    nitrogen_kg_ha: float | None = None
    phosphorus_kg_ha: float | None = None
    potassium_kg_ha: float | None = None
    source: str | None = None


class WeatherConditions(Base):
    annual_rainfall_mm: float | None = None
    season_rainfall_mm: float | None = None
    avg_temp_c: float | None = None
    source: str | None = None


class Conditions(Base):
    soil: SoilConditions
    weather: WeatherConditions
    ndvi_current: float | None = None
    data_completeness: float = Field(ge=0, le=1)


class ResolvedLocation(Base):
    state_code: str
    district_code: str
    district_name: str
    centroid: list[float] = Field(min_length=2, max_length=2)
    area_ha: float


class Reason(Base):
    factor: str
    impact: Impact
    detail: str


class DateWindow(Base):
    start: date
    end: date


class CropCalendar(Base):
    sowing_window: DateWindow
    harvest_window: DateWindow
    duration_days: int


class Economics(Base):
    """Whole-plot figures except the *_per_ha fields.

    Any field may be null when the source data is unavailable. The frontend
    renders null as an em dash, never as zero - contract section 4.
    """

    expected_yield_t_ha: float | None = None
    input_cost_per_ha: int | None = None
    expected_price_per_quintal: int | None = None
    gross_revenue: int | None = None
    net_margin: int | None = None
    margin_per_ha: int | None = None
    price_source: str | None = None
    price_as_of: date | None = None


class Risk(Base):
    type: str
    name: str
    severity: str


class Recommendation(Base):
    rank: int = Field(ge=1)
    crop_code: str
    name: str
    variety_suggested: str | None = None
    score: float = Field(ge=0, le=1)
    confidence: Confidence
    reasons: list[Reason] = Field(min_length=2, max_length=4)
    calendar: CropCalendar
    economics: Economics
    risks: list[Risk] = Field(default_factory=list)


class Warning_(Base):
    code: str
    message: str


class RecommendationResponse(Base):
    request_id: str
    generated_at: datetime
    location_resolved: ResolvedLocation
    conditions: Conditions
    recommendations: list[Recommendation]
    # May be empty, but always present.
    warnings: list[Warning_] = Field(default_factory=list)


class FieldSummaryResponse(Base):
    location_resolved: ResolvedLocation
    conditions: Conditions


# --------------------------------------------------------------------- meta


class District(Base):
    district_code: str
    district_name: str
    centroid: list[float] = Field(min_length=2, max_length=2)


class State(Base):
    state_code: str
    state_name: str
    districts: list[District]


class DistrictsResponse(Base):
    states: list[State]


class Crop(Base):
    crop_code: str
    name: str
    name_hi: str | None = None
    category: str
    seasons: list[Season]


class CropsResponse(Base):
    crops: list[Crop]


# ------------------------------------------------------------------- prices


class PricePoint(Base):
    date: date
    modal_price: int
    min_price: int
    max_price: int
    mandi: str


class PricesResponse(Base):
    crop_code: str
    unit: str = "per_quintal"
    series: list[PricePoint]
    source: str
    fetched_at: datetime


# ------------------------------------------------ spectral indices (additive)
# Added after the v1 freeze. Additive only: no existing shape changes, so older
# clients are unaffected. See docs/api-contract.md changelog.


class SpectralIndex(Base):
    key: str
    name: str
    value: float | None = None
    range_min: float
    range_max: float
    interpretation: str
    formula: str


class NdviHistoryPoint(Base):
    date: date
    ndvi: float | None = None


class IndicesRequest(Base):
    location: Location


class IndicesResponse(Base):
    location_resolved: ResolvedLocation
    observed_on: date | None = None
    cloud_cover_pct: float | None = None
    indices: list[SpectralIndex]
    history: list[NdviHistoryPoint] = Field(default_factory=list)
    source: str
    tile_url_template: str | None = None


class HealthResponse(Base):
    status: str
    version: str
    geo_service: str
    db: str
