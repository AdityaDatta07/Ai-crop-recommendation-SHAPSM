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
from typing import Any, Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Season = Literal["kharif", "rabi", "zaid"]
Irrigation = Literal["rainfed", "canal", "tubewell", "drip"]
Confidence = Literal["high", "medium", "low"]
Impact = Literal["positive", "neutral", "negative"]
Level = Literal["low", "medium", "high"]

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
    # What they grew here last season. One crop code — deliberately not a form
    # of yields, costs and sale prices. We already know how to value a crop on
    # this field; asking the farmer to re-enter what we can compute would be
    # work for them and a second source of truth for us.
    previous_crop: str | None = None
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
    """Where the satellite actually looked.

    `precision` matters more than it appears. A district selection samples the
    district's stored centroid, which is generally its main town, so every
    figure derived from it describes that town rather than a field. The UI has
    to be able to say so.
    """

    state_code: str
    district_code: str
    district_name: str
    centroid: list[float] = Field(min_length=2, max_length=2)
    area_ha: float
    area_acres: float | None = None
    precision: Literal["field", "point", "district"] = "field"


class Reason(Base):
    factor: str
    impact: Impact
    detail: str
    """English sentence. The fallback for any client without a translation."""

    code: str = ""
    """Which message this is, e.g. "ph_inside_band". See LOCALISED MESSAGES below."""

    params: dict[str, Any] = Field(default_factory=dict)
    """The values to slot into it, e.g. {"ph": 7.5, "low": 6.0, "high": 7.5}."""


class DateWindow(Base):
    start: date
    end: date


class CropCalendar(Base):
    sowing_window: DateWindow
    harvest_window: DateWindow
    duration_days: int
    days_until_sowing: int | None = None
    window_status: Literal["open", "upcoming", "closed_this_year"] | None = None


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

    # Per-acre figures, computed server-side. Indian farmers think in acres far
    # more than hectares, and converting in the browser would put arithmetic in
    # the one place this app must never do arithmetic.
    input_cost_per_acre: int | None = None
    margin_per_acre: int | None = None
    expected_yield_t_acre: float | None = None


class Attribution(Base):
    """One factor's share of the score.

    For a weighted sum these ARE the Shapley values, not an approximation of
    them — contributions sum to the score exactly. Worth knowing if anyone asks
    why this is not a SHAP plot: over a linear model, SHAP would compute these
    same numbers the slow way.
    """

    factor: str
    contribution: float
    headroom: float
    score: float
    impact: Impact
    detail: str
    """English. Shares the ranker's reason codes — same sentence, same source."""

    code: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class Counterfactual(Base):
    """What would have to change for this crop to rank higher.

    Exact, not estimated: the ranker is a weighted sum, so this is the model
    re-run with one input altered, not an approximation of its behaviour.
    """

    factor: str
    kind: Literal["threshold", "fragility", "limiting"]
    current_value: str
    target_value: str | None = None
    score_gain: float
    rank_gain: int
    params: dict[str, Any] = Field(default_factory=dict)
    """Values for the localised sentence. `kind` selects which sentence."""
    message: str


class PriceOutlook(Base):
    """Projected price for the month the crop is actually sold.

    `basis` says how the figure was arrived at, and the UI must render each
    value differently — a median over recorded history and an MSP floor are
    different kinds of claim and must not look alike.
    """

    harvest_month: str | None = None
    expected_per_quintal: int | None = None
    low_per_quintal: int | None = None
    high_per_quintal: int | None = None
    msp_floor_per_quintal: int | None = None
    current_per_quintal: int | None = None
    basis: Literal["seasonal_history", "msp_floor", "current_only", "none"]
    observations_used: int = 0
    explanation: str
    explanation_code: str = ""
    explanation_params: dict[str, Any] = Field(default_factory=dict)
    below_msp_by: int | None = None


class Risk(Base):
    type: str
    name: str
    severity: str


class RotationNote(Base):
    """How this crop sits against what grew here last season.

    Surfaced per recommendation rather than left to the `reasons` list. Reasons
    show the four strongest factors, so rotation only appeared when it happened
    to be among them — which made a feature the farmer explicitly supplied
    input for effectively invisible.
    """

    score: float
    code: str
    params: dict[str, Any] = Field(default_factory=dict)


class Recommendation(Base):
    rank: int = Field(ge=1)
    crop_code: str
    name: str
    variety_suggested: str | None = None
    score: float = Field(ge=0, le=1)
    confidence: Confidence
    reasons: list[Reason] = Field(min_length=2, max_length=4)

    rank_by_return: int | None = None
    """Position if these crops were ordered by money instead of by fit.

    `rank` answers "what suits this field best"; this answers "what earns most
    on our figures". They are different questions and the app was only showing
    one of them, which made a farmer looking at a lower-ranked, better-paying
    crop think the ranking was broken.

    Null when the crop has no published price. A crop whose earnings we cannot
    compute cannot be placed in an ordering by earnings, and guessing a
    position for it would be inventing the very number we declined to state.
    """
    # Present only when the farmer named last season's crop. See RotationNote.
    rotation: RotationNote | None = None
    calendar: CropCalendar
    economics: Economics
    # Today's price is nearly irrelevant to a sowing decision; this projects to
    # the month the crop is actually sold.
    price_outlook: PriceOutlook | None = None
    # "What would have to change" — the question a farmer asks after "why".
    attribution: list[Attribution] = Field(default_factory=list)
    counterfactuals: list[Counterfactual] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)


class Warning_(Base):
    """A caution the farmer should read before acting.

    LOCALISED MESSAGES
    ------------------
    `message` is English. Translating it server-side would mean a second copy of
    the frontend's translation files living in Python, and two copies drift.

    So the server sends what it knows — a stable `code` and the `params` that go
    in the sentence — and the client renders it from the dictionary it already
    has. A client with no dictionary falls back to `message` and still shows
    something true, just in English.

    Consequence worth stating: `code` and the keys in `params` are part of the
    contract. Renaming either silently reverts a farmer to English.
    """

    code: str
    message: str
    params: dict[str, Any] = Field(default_factory=dict)


class ComparisonSide(Base):
    """One crop valued on this field, for a like-for-like comparison."""

    crop_code: str
    name: str
    rank: int | None = None
    """Where it places in this season's ranking. None if it cannot grow here now."""
    score: float | None = None
    net_margin: int | None = None
    margin_per_ha: int | None = None
    margin_per_acre: int | None = None
    expected_yield_t_ha: float | None = None


class CropComparison(Base):
    """Last season's crop against this season's recommendation.

    Both sides are scored by the same engine on the same field with the same
    prices, so the difference is attributable to the crop and nothing else.
    """

    previous: ComparisonSide
    recommended: ComparisonSide
    margin_difference: int | None = None
    rank_difference: int | None = None
    same_crop: bool = False
    verdict: str
    """English. Localised client-side from verdict_code — see Warning_."""

    verdict_code: str = ""
    verdict_params: dict[str, Any] = Field(default_factory=dict)


class AdviceConcentration(Base):
    """How often THIS TOOL ranked this crop first, in this district and season.

    Read the field names literally. `advisories_total` counts advisories this
    application issued; it is not a count of farmers, plots, hectares or sowing
    intentions, and no client may word it as one. We have no visibility of what
    anyone actually plants, and a district-level sowing figure does not exist in
    any public feed in time to act on.

    It is worth showing anyway, for a reason that runs the other way: an
    advisory taken seriously at scale becomes a cause of the glut it is meant to
    warn about. If this tool tells everyone in a district to plant the same
    thing, that is a fact about the tool the farmer is entitled to know.

    `share` is null below the minimum sample. See services/crowding.py.
    """

    crop_code: str
    times_ranked_first: int
    advisories_total: int
    share: float | None = None
    band: Literal["crowded", "common", "uncommon", "never", "unknown"]
    code: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class HarvestDip(Base):
    """What this crop fetched in its harvest month against the rest of the year.

    Backward-looking by construction: it describes harvests that already
    happened, from mandi prices we recorded. It is not a forecast for the coming
    one, and `crowding.dip_is_backward_looking` is attached whenever a band is
    produced so the UI cannot omit that.

    `scope` says whose market this is. "district" is the local record;
    "national" means the district had too little history and this is every
    district pooled — genuinely useful, but a different claim, and the UI must
    distinguish them the same way `precision` does for location.
    """

    crop_code: str
    harvest_month: int | None = None
    harvest_median: int | None = None
    other_median: int | None = None
    dip_fraction: float | None = None
    band: Literal["steep", "mild", "none", "unknown"]
    observations: int = 0
    scope: Literal["district", "national", "none"] = "none"
    code: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class Crowding(Base):
    """Both crowding signals for one crop, plus the caveats that must be shown."""

    crop_code: str
    name: str = ""
    concentration: AdviceConcentration
    dip: HarvestDip
    caveat_codes: list[str] = Field(default_factory=list)
    seeded_advisories: int = 0
    """How many of `advisories_total` were generated by the seeding script
    rather than requested by a person. Non-zero attaches
    `crowding.includes_seeded` so the UI cannot omit it."""


class WaterBudget(Base):
    """What the crop needs, what the rain gives, and the gap between them.

    `season_rainfall_mm` is a THIRTY-YEAR NORMAL, not a forecast. The UI must
    say so wherever this is shown: a budget that balances on the average still
    fails in a dry year, and Indian monsoon totals swing widely around their
    own mean.
    """

    crop_code: str
    name: str
    requirement_mm: int
    comfortable_mm: int
    season_rainfall_mm: float | None = None
    effective_rainfall_mm: float | None = None
    """What the crop can use after runoff and percolation. Always < what fell."""

    deficit_mm: float | None = None
    deficit_m3: float | None = None
    waterings: int | None = None
    """To reach the MINIMUM of the crop's band. See waterings_comfortable."""

    waterings_comfortable: int | None = None
    deficit_comfortable_mm: float | None = None
    surplus_mm: float | None = None
    status: Literal[
        "rain_sufficient", "needs_irrigation", "cannot_meet", "surplus", "unknown"
    ] = "unknown"
    can_be_met: bool = True


class RiskExposure(Base):
    """One crop's exposure on three axes we can cite a source for."""

    crop_code: str
    name: str
    agronomic: Level
    price: Level
    water: Level
    risk_types: list[str] = Field(default_factory=list)
    severe_risks: list[str] = Field(default_factory=list)
    drivers: list[str] = Field(default_factory=list)
    """Message codes naming what drives it. Localised client-side."""


class Allocation(Base):
    crop_code: str
    name: str
    share: float = Field(ge=0, le=1)
    area_ha: float
    net_margin: int | None = None


class RiskPlan(Base):
    """Exposure, and whether splitting the field would actually reduce it.

    `plan` is empty whenever splitting would not help — a plot too small to
    divide, no partner crop that suits the field, or every candidate failing for
    the same reasons the top crop does. `verdict_code` says which, and that is
    the useful answer in each case rather than a fallback.

    Not a portfolio optimisation. The shares are a stated rule of thumb; see
    apps/api/services/diversification.py for why a real one is not possible with
    the data anyone has at this resolution.
    """

    exposures: list[RiskExposure] = Field(default_factory=list)
    plan: list[Allocation] = Field(default_factory=list)
    overlap: float | None = None
    """0 = the two crops fail for unrelated reasons, 1 = they fail together."""

    combined_margin: int | None = None

    single_crop_margin: int | None = None
    """The best a single crop could earn here — by money, not by rank.

    Ranking is by agronomic fit, so rank 1 is not always the best earner. The
    split has to be compared against the best single option a farmer actually
    has, or the comparison flatters it.
    """

    single_crop_name: str = ""
    single_crop_code: str = ""
    margin_given_up: int | None = None
    """What the split costs against putting it all in the top crop.

    Reported rather than hidden. Diversifying nearly always earns less on
    average; that is what it pays for safety with, and a farmer is entitled to
    see the price before deciding.
    """

    verdict_code: str = ""
    verdict_params: dict[str, Any] = Field(default_factory=dict)


class RequestEcho(Base):
    """The inputs this answer was computed from.

    Two reasons this is worth the bytes:

    1. A shareable /r/<id> link is only traceable if you can see what was asked,
       not just what came back. The printed advisory cites a request_id; this is
       what that id resolves to.
    2. The what-if calculator has to re-ask the same question with one value
       changed. Without the original inputs it would have to guess at the rest,
       and a what-if built on guessed inputs is not a comparison of anything.

    Deliberately the request as RECEIVED, before any defaulting or resolution —
    location_resolved already carries what the server made of it.
    """

    location: Location
    season: Season
    area_ha: float
    irrigation: Irrigation | None = None
    soil_test: SoilTest | None = None
    previous_crop: str | None = None


class RecommendationResponse(Base):
    request_id: str
    generated_at: datetime
    location_resolved: ResolvedLocation
    conditions: Conditions
    recommendations: list[Recommendation]
    # Present only when the farmer told us what they grew last season.
    comparison: CropComparison | None = None
    # May be empty, but always present.
    warnings: list[Warning_] = Field(default_factory=list)
    # What was asked. See RequestEcho.
    request_echo: RequestEcho | None = None
    # Exposure and whether splitting the field helps. See RiskPlan.
    risk: RiskPlan | None = None
    # Water need against rainfall, per crop. See WaterBudget.
    water: list[WaterBudget] = Field(default_factory=list)
    # District crowding, per crop. Counts of OUR OWN ADVICE plus the
    # harvest-month price record. Never a count of farmers. See Crowding.
    crowding: list[Crowding] = Field(default_factory=list)


class MspCrop(Base):
    """One notified crop.

    `crop_code` is null when the government sets an MSP for a crop this system
    does not rank — a farmer looking up moong should get an answer even though
    we never recommend it.

    `cost_a2fl_per_quintal` is null for grades whose cost is not compiled
    separately (Paddy Grade A, Jowar Maldandi, long-staple cotton). Copying the
    sibling grade's figure would put a different crop's number under this one's
    name.
    """

    name: str
    name_hi: str = ""
    group: str
    season: str
    crop_code: str | None = None
    msp_per_quintal: int
    cost_a2fl_per_quintal: int | None = None


class MspSource(Base):
    key: str
    title: str
    publisher: str
    published: str
    url: str


class MspUnlisted(Base):
    """Supported but not in the two CCEA releases, so deliberately unpriced."""

    name: str
    name_hi: str = ""
    note: str = ""


class MspResponse(Base):
    marketing_season: str
    updated: str
    crops: list[MspCrop]
    sources: dict[str, MspSource]
    not_listed_here: list[MspUnlisted] = Field(default_factory=list)


class ChatRequest(Base):
    """One question about one already-generated advisory.

    Note what is NOT here: the advisory itself. The server fetches it by
    `request_id` from its own store. A client that could supply the grounding
    document could supply a fictional one, and the model would answer from it
    faithfully.
    """

    message: str = Field(min_length=1, max_length=1000)
    turn: int = Field(default=1, ge=1)
    """Which question this is in the conversation. Enforces the session cap."""


class ChatResponse(Base):
    """`source` is the honesty dial and the UI renders each value differently.

    - `refusal`  — deliberately out of scope. `refusal_category` says which
                   boundary, so the UI can redirect to the right place instead
                   of showing one generic brush-off.
    - `template` — answered from the advisory by deterministic code. Render
                   `code` and `params` through the usual i18n path.
    - `model`    — free prose from the LLM, already checked for figures that
                   are not in the grounding document.
    - `unavailable` — no key, a failed call, or a reply that failed validation.
                   All three say so rather than showing something unverified.
    """

    source: Literal["refusal", "template", "model", "unavailable"]
    code: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    text: str = ""
    refusal_category: str | None = None


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
    """English and Hindi are separate fields because the v1 contract froze them
    that way. Everything since lives in `names`."""

    names: dict[str, str] = Field(default_factory=dict)
    """Locale code -> crop name, for every language the app speaks. The client
    picks its own; the server does not decide for it. Additive, so a client
    built against v1 ignores it."""

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


class CropCycle(Base):
    """One rise and fall of the canopy: a crop grown and taken off."""

    peak_month: str
    peak_ndvi: float
    season: Season
    start_month: str
    end_month: str
    months: int


class CropHistory(Base):
    """What this field has been doing, read off two years of NDVI.

    NOT crop identification. Telling wheat from barley by spectral signature
    needs labelled ground-truth we do not have, and a confident wrong answer
    about somebody's own field would discredit everything else on the page.
    This says how OFTEN the plot is cropped and WHEN, which optical imagery
    genuinely supports.

    The error runs one way. Sentinel-2 is optical and kharif is the cloudiest
    season, so a missed monsoon peak makes a double-cropped field look
    single-cropped. `season_coverage` and `caveat_codes` exist so the UI can
    say that rather than presenting an undercount as a finding.
    """

    intensity: Literal[
        "single", "double", "triple", "fallow", "uncropped", "unknown"
    ]
    cycles: list[CropCycle] = Field(default_factory=list)
    cycles_per_year: float = 0.0
    seasons_used: list[str] = Field(default_factory=list)
    fallow_months: int = 0
    observed_months: int = 0
    total_months: int = 0
    season_coverage: dict[str, float] = Field(default_factory=dict)
    confidence: Confidence = "low"
    caveat_codes: list[str] = Field(default_factory=list)


class Productivity(Base):
    """How much this plot grows, against the land around it.

    The measure is NDVI amplitude — the swing between bare ground and peak
    canopy across one season. Amplitude rather than peak, because an orchard
    or scrub sits high all year without ever growing a crop.

    NOT A YIELD. Biomass and grain are related but not the same: a lush crop
    that lodges before harvest scores well here and yields badly. And the
    neighbours may be growing something else entirely — a pulse will never
    match a paddy for amplitude. The UI must carry both caveats.
    """

    plot_amplitude: float | None = None
    percentile: int | None = None
    band: Literal[
        "well_above", "above", "typical", "below", "well_below", "unknown"
    ] = "unknown"
    percentiles: dict[str, float] = Field(default_factory=dict)
    neighbourhood_km: float = 0.0
    sample_pixels: int = 0
    caveat_codes: list[str] = Field(default_factory=list)


class IndicesRequest(Base):
    location: Location


class IndicesResponse(Base):
    location_resolved: ResolvedLocation
    observed_on: date | None = None
    cloud_cover_pct: float | None = None
    indices: list[SpectralIndex]
    history: list[NdviHistoryPoint] = Field(default_factory=list)
    # Derived from `history` at no extra cost — see CropHistory.
    crop_history: CropHistory | None = None
    # Amplitude against the surrounding farmland. See Productivity.
    productivity: Productivity | None = None
    source: str
    tile_url_template: str | None = None


class HealthResponse(Base):
    status: str
    version: str
    geo_service: str
    db: str
