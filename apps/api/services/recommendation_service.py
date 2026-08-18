"""The orchestrator.

One function owns the main request path, in the order architecture.md section 5
specifies: resolve location, sample conditions, filter candidates, rank, price
the top N, compute economics, persist.

Ordering rationale, restated because it is easy to "optimise" wrongly: geo runs
first because ranking depends on soil and weather. Prices are fetched AFTER
ranking and only for the crops being returned - fetching prices for all 16 crops
to return 5 would waste the slowest call in the chain.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date, datetime, timezone

from ulid import ULID

from apps.api.core import errors
from apps.api.core.reference import ReferenceData
from apps.api.schemas import contract as api
from apps.api.services import economics as economics_module
from apps.api.services.calendar_service import resolve_calendar
from apps.api.services.price_service import PriceService
from services.geo import get_conditions, resolve_admin
from services.geo.types import Conditions, GeoUnavailable, InvalidGeometry
from services.geo.types import Location as GeoLocation
from services.ml import Constraints, RankingInput, RulesRanker, project_yield
from services.ml.types import CropSpec, ScoredCrop

logger = logging.getLogger(__name__)


def new_request_id() -> str:
    """Unguessable, sortable. Doubles as the capability token for replay links,
    which is why it must not be a sequential integer - see db/policies.sql."""
    return f"req_{ULID()}"


def _to_geo_location(location: api.Location) -> GeoLocation:
    if isinstance(location, api.PointLocation):
        return GeoLocation(type="point", lat=location.lat, lon=location.lon)
    if isinstance(location, api.AdminLocation):
        return GeoLocation(
            type="admin",
            state_code=location.state_code,
            district_code=location.district_code,
        )
    return GeoLocation(type="polygon", coordinates=location.geometry.coordinates)


SOIL_TEST_SOURCE = "Farmer-supplied Soil Health Card values"


def _apply_soil_test(conditions: Conditions, soil_test: api.SoilTest | None) -> Conditions:
    """Overlay the farmer's Soil Health Card readings onto sampled conditions.

    A lab measurement of this specific field beats any modelled or district
    figure, so supplied values win outright. Each nutrient is applied
    independently — a card showing only nitrogen still improves the result.

    Completeness rises to match, because it now genuinely reflects how much of
    what the recommendation needs we actually have.
    """
    if soil_test is None or not soil_test.has_any:
        return conditions

    supplied = [
        value
        for value in (
            soil_test.nitrogen_kg_ha,
            soil_test.phosphorus_kg_ha,
            soil_test.potassium_kg_ha,
        )
        if value is not None
    ]

    soil = conditions.soil
    sources = [part for part in (soil.source, SOIL_TEST_SOURCE) if part]

    return replace(
        conditions,
        soil=replace(
            soil,
            nitrogen_kg_ha=soil_test.nitrogen_kg_ha
            if soil_test.nitrogen_kg_ha is not None
            else soil.nitrogen_kg_ha,
            phosphorus_kg_ha=soil_test.phosphorus_kg_ha
            if soil_test.phosphorus_kg_ha is not None
            else soil.phosphorus_kg_ha,
            potassium_kg_ha=soil_test.potassium_kg_ha
            if soil_test.potassium_kg_ha is not None
            else soil.potassium_kg_ha,
            source=" + ".join(sources),
        ),
        # Three nutrients are counted as unsourced in services/geo. Each one the
        # farmer supplies closes a third of that gap.
        data_completeness=min(
            1.0, round(conditions.data_completeness + 0.125 * len(supplied), 2)
        ),
    )


def _conditions_to_api(conditions: Conditions) -> api.Conditions:
    return api.Conditions(
        soil=api.SoilConditions(
            texture=conditions.soil.texture,
            ph=conditions.soil.ph,
            organic_carbon_pct=conditions.soil.organic_carbon_pct,
            nitrogen_kg_ha=conditions.soil.nitrogen_kg_ha,
            phosphorus_kg_ha=conditions.soil.phosphorus_kg_ha,
            potassium_kg_ha=conditions.soil.potassium_kg_ha,
            source=conditions.soil.source,
        ),
        weather=api.WeatherConditions(
            annual_rainfall_mm=conditions.weather.annual_rainfall_mm,
            season_rainfall_mm=conditions.weather.season_rainfall_mm,
            avg_temp_c=conditions.weather.avg_temp_c,
            source=conditions.weather.source,
        ),
        ndvi_current=conditions.ndvi_current,
        data_completeness=conditions.data_completeness,
    )


def resolve_place(location: api.Location, area_ha: float):
    """Shared by /recommendations and /geo/field-summary."""
    try:
        return resolve_admin(_to_geo_location(location), area_ha)
    except InvalidGeometry as exc:
        # The input is out of bounds, not missing - 400, and fixable by redrawing.
        raise errors.InvalidLocation(str(exc), field="location.geometry") from exc
    except GeoUnavailable as exc:
        # We have no coverage there - 422, and not the farmer's fault.
        raise errors.NoDataForLocation(str(exc), field="location") from exc


def build_field_summary(location: api.Location, area_ha: float = 1.0) -> api.FieldSummaryResponse:
    place = resolve_place(location, area_ha)
    conditions = get_conditions(place)
    return api.FieldSummaryResponse(
        location_resolved=api.ResolvedLocation(
            state_code=place.state_code,
            district_code=place.district_code,
            district_name=place.district_name,
            centroid=list(place.centroid),
            area_ha=place.area_ha,
        ),
        conditions=_conditions_to_api(conditions),
    )


def _collect_warnings(
    conditions: Conditions,
    reference: ReferenceData,
    unpriced: list[str],
) -> list[api.Warning_]:
    """Everything the farmer should know before acting, gathered in one place."""
    warnings: list[api.Warning_] = []

    if conditions.data_completeness < 0.6:
        warnings.append(
            api.Warning_(
                code="LOW_DATA_COMPLETENESS",
                message=(
                    f"Only {conditions.data_completeness:.0%} of the expected soil and weather "
                    "inputs were available. Treat this ranking as indicative."
                ),
            )
        )

    if conditions.soil.nitrogen_kg_ha is None:
        warnings.append(
            api.Warning_(
                code="PARTIAL_SOIL_DATA",
                message=(
                    "No soil nutrient values for this field. No satellite can measure "
                    "nitrogen, phosphorus or potassium — enter them from your Soil "
                    "Health Card for a sharper recommendation."
                ),
            )
        )

    if unpriced:
        warnings.append(
            api.Warning_(
                code="PRICE_UNAVAILABLE",
                message=(
                    "No published price for "
                    + ", ".join(unpriced)
                    + ". Their revenue figures are left blank rather than guessed."
                ),
            )
        )

    # Always emitted while the agronomic thresholds are unverified. This is the
    # honest channel for it: the contract derives `confidence` from data
    # completeness, so overloading confidence to also mean "our reference data
    # is provisional" would misreport how much field data we actually had.
    if reference.agronomy_source.is_provisional:
        warnings.append(
            api.Warning_(
                code="PROVISIONAL_AGRONOMY",
                message=(
                    "Suitability thresholds are provisional and pending expert review. "
                    "Check against local extension advice before sowing."
                ),
            )
        )

    return warnings


def _build_recommendation(
    rank: int,
    scored: ScoredCrop,
    crop: CropSpec,
    ranking_input: RankingInput,
    area_ha: float,
    price_service: PriceService,
    district_code: str,
    today: date,
    sowing_date: date | None,
) -> api.Recommendation:
    forecast = project_yield(crop, scored.score, ranking_input)
    price = price_service.for_crop(crop, district_code)

    result = economics_module.compute(
        expected_yield_t_ha=forecast.t_per_ha,
        published_yield_kg_per_ha=crop.yield_kg_per_ha,
        cost_a2fl_per_quintal=crop.cost_a2fl_per_quintal,
        price_per_quintal=price.per_quintal,
        area_ha=area_ha,
        price_source=price.source,
        price_as_of=price.as_of,
    )

    sow_start, sow_end, harvest_start, harvest_end = resolve_calendar(crop, today, sowing_date)

    return api.Recommendation(
        rank=rank,
        crop_code=crop.crop_code,
        name=crop.name,
        variety_suggested=crop.varieties[0] if crop.varieties else None,
        score=round(scored.score, 4),
        confidence=scored.confidence,
        reasons=[
            api.Reason(factor=factor.factor, impact=factor.impact, detail=factor.detail)
            for factor in scored.reasons
        ],
        calendar=api.CropCalendar(
            sowing_window=api.DateWindow(start=sow_start, end=sow_end),
            harvest_window=api.DateWindow(start=harvest_start, end=harvest_end),
            duration_days=crop.duration_days,
        ),
        economics=api.Economics(
            expected_yield_t_ha=result.expected_yield_t_ha,
            input_cost_per_ha=result.input_cost_per_ha,
            expected_price_per_quintal=result.expected_price_per_quintal,
            gross_revenue=result.gross_revenue,
            net_margin=result.net_margin,
            margin_per_ha=result.margin_per_ha,
            price_source=result.price_source,
            price_as_of=result.price_as_of,
        ),
        risks=[
            api.Risk(type=risk.type, name=risk.name, severity=risk.severity)
            for risk in crop.risks
        ],
    )


def recommend(
    request: api.RecommendationRequest,
    reference: ReferenceData,
    *,
    request_id: str | None = None,
    today: date | None = None,
) -> api.RecommendationResponse:
    request_id = request_id or new_request_id()
    today = today or datetime.now(timezone.utc).date()

    # 1. Where is this field?
    place = resolve_place(request.location, request.area_ha)

    # 2. What are its conditions? Never raises - degrades instead.
    conditions = get_conditions(place)

    # 2b. The farmer's own soil test, if they have their card to hand.
    conditions = _apply_soil_test(conditions, request.soil_test)

    # 3. Which crops are even plausible this season?
    candidates = reference.crops_for_season(request.season)
    if not candidates:
        raise errors.UnsupportedSeason(
            f"No crops in the reference set are calendared for the {request.season} season yet.",
            field="season",
        )

    # 4. Rank them.
    ranking_input = RankingInput(
        ph=conditions.soil.ph,
        texture=conditions.soil.texture,
        nitrogen_kg_ha=conditions.soil.nitrogen_kg_ha,
        avg_temp_c=conditions.weather.avg_temp_c,
        season_rainfall_mm=conditions.weather.season_rainfall_mm,
        annual_rainfall_mm=conditions.weather.annual_rainfall_mm,
        irrigation=request.irrigation,
        data_completeness=conditions.data_completeness,
    )
    ranked = RulesRanker().rank(
        ranking_input,
        candidates,
        Constraints(
            exclude_crops=tuple(request.constraints.exclude_crops),
            max_input_cost=request.constraints.max_input_cost,
            organic_only=request.constraints.organic_only,
        ),
    )

    # 5. Apply the cost ceiling after ranking, where the derived cost exists.
    if request.constraints.max_input_cost is not None:
        ceiling = request.constraints.max_input_cost
        affordable = []
        for scored in ranked:
            crop = reference.crops[scored.crop_code]
            cost = economics_module.input_cost_per_ha(
                crop.cost_a2fl_per_quintal, crop.yield_kg_per_ha
            )
            # An unknown cost is not proof of affordability, but excluding it
            # would hide crops we simply have no cost figure for. Keep it and
            # let the null cost on screen speak for itself.
            if cost is None or cost <= ceiling:
                affordable.append(scored)
        ranked = affordable

    top = ranked[: request.limit]

    # 6. Price and cost only the crops actually being returned.
    price_service = PriceService(reference)
    recommendations: list[api.Recommendation] = []
    unpriced: list[str] = []

    for position, scored in enumerate(top, start=1):
        crop = reference.crops[scored.crop_code]
        recommendation = _build_recommendation(
            rank=position,
            scored=scored,
            crop=crop,
            ranking_input=ranking_input,
            area_ha=place.area_ha,
            price_service=price_service,
            district_code=place.district_code,
            today=today,
            sowing_date=request.sowing_date,
        )
        if recommendation.economics.expected_price_per_quintal is None:
            unpriced.append(crop.name)
        recommendations.append(recommendation)

    return api.RecommendationResponse(
        request_id=request_id,
        generated_at=datetime.now(timezone.utc),
        location_resolved=api.ResolvedLocation(
            state_code=place.state_code,
            district_code=place.district_code,
            district_name=place.district_name,
            centroid=list(place.centroid),
            area_ha=place.area_ha,
        ),
        conditions=_conditions_to_api(conditions),
        recommendations=recommendations,
        warnings=_collect_warnings(conditions, reference, unpriced),
    )


def build_indices(location: api.Location, area_ha: float = 1.0) -> api.IndicesResponse:
    """Spectral indices for a location, for the map overlay and history chart."""
    from services.geo import get_indices

    place = resolve_place(location, area_ha)
    result = get_indices(place)

    return api.IndicesResponse(
        location_resolved=api.ResolvedLocation(
            state_code=place.state_code,
            district_code=place.district_code,
            district_name=place.district_name,
            centroid=list(place.centroid),
            area_ha=place.area_ha,
        ),
        observed_on=result.observed_on,
        cloud_cover_pct=result.cloud_cover_pct,
        indices=[
            api.SpectralIndex(
                key=index.key,
                name=index.name,
                value=index.value,
                range_min=index.range_min,
                range_max=index.range_max,
                interpretation=index.interpretation,
                formula=index.formula,
            )
            for index in result.indices
        ],
        history=[
            api.NdviHistoryPoint(date=point.date, ndvi=point.ndvi) for point in result.history
        ],
        source=result.source,
        tile_url_template=result.tile_url_template,
    )
