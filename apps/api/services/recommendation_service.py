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
from pathlib import Path
from datetime import date, datetime, timezone
from typing import Sequence

from ulid import ULID

from apps.api.core import errors
from apps.api.core.reference import ReferenceData
from apps.api.schemas import contract as api
from apps.api.services import diversification
from apps.api.services import crowding as crowding_module
from apps.api.services import water_budget as water_module
from apps.api.services import economics as economics_module
from apps.api.services.calendar_service import resolve_calendar_full
from apps.api.services.comparison import build_comparison
from apps.api.services.price_outlook import build_outlook
from apps.api.services.price_service import PriceService
from services.geo import get_conditions, resolve_admin
from services.geo.types import Conditions, GeoUnavailable, InvalidGeometry
from services.geo.types import Location as GeoLocation
from services.ml import Constraints, RankingInput, RulesRanker, project_yield
from services.ml.counterfactual import attribute, find_counterfactuals
from services.ml.crop_history import analyse as analyse_crop_history
from services.ml.productivity import analyse as analyse_productivity
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


def build_field_summary(
    location: api.Location,
    area_ha: float = 1.0,
    season: str | None = None,
) -> api.FieldSummaryResponse:
    """The map preview, before a season has necessarily been chosen.

    `season` is optional here on purpose: the field summary is fetched as soon
    as a location is picked, which can be before the farmer has said which
    season they are planning. With no season the geo service falls back to the
    calendar, which is the right guess when there is nothing better.
    """
    place = resolve_place(location, area_ha)
    conditions = get_conditions(place, season)
    return api.FieldSummaryResponse(
        location_resolved=api.ResolvedLocation(
            state_code=place.state_code,
            district_code=place.district_code,
            district_name=place.district_name,
            centroid=list(place.centroid),
            area_ha=place.area_ha,
            precision=place.precision,
        ),
        conditions=_conditions_to_api(conditions),
    )


def _collect_warnings(
    conditions: Conditions,
    reference: ReferenceData,
    unpriced: list[tuple[str, str]],
    closed_season: str | None = None,
) -> list[api.Warning_]:
    """Everything the farmer should know before acting, gathered in one place."""
    warnings: list[api.Warning_] = []

    if closed_season:
        warnings.append(
            api.Warning_(
                code="SOWING_WINDOW_CLOSED",
                params={"season": closed_season},
                message=(
                    f"The {closed_season} sowing window has already closed this year. "
                    "The dates below are for next season, so treat this as planning "
                    "ahead rather than something to act on now."
                ),
            )
        )

    if conditions.data_completeness < 0.6:
        warnings.append(
            api.Warning_(
                code="LOW_DATA_COMPLETENESS",
                params={"percent": round(conditions.data_completeness * 100)},
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
                params={
                    "crops": ", ".join(name for _, name in unpriced),
                    "crops_code": ",".join(code for code, _ in unpriced),
                },
                message=(
                    "No published price for "
                    + ", ".join(name for _, name in unpriced)
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
    counterfactuals: list | None = None,
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

    schedule = resolve_calendar_full(crop, today, sowing_date)
    sow_start, sow_end = schedule.sowing_start, schedule.sowing_end
    harvest_start, harvest_end = schedule.harvest_start, schedule.harvest_end

    # What will this fetch when it is actually sold, not today.
    history = (
        price_service.history.prices_in_month(crop.crop_code, harvest_start.month)
        if price_service.history is not None
        else []
    )
    outlook = build_outlook(
        crop_name=crop.name,
        crop_code=crop.crop_code,
        harvest_start=harvest_start,
        msp_floor=crop.price_per_quintal,
        current_price=price.per_quintal,
        harvest_month_history=history,
    )

    return api.Recommendation(
        rank=rank,
        crop_code=crop.crop_code,
        name=crop.name,
        variety_suggested=crop.varieties[0] if crop.varieties else None,
        score=round(scored.score, 4),
        confidence=scored.confidence,
        reasons=[
            api.Reason(
                factor=factor.factor,
                impact=factor.impact,
                detail=factor.detail,
                code=factor.code,
                params=factor.params,
            )
            for factor in scored.reasons
        ],
        rotation=next(
            (
                api.RotationNote(score=f.score, code=f.code, params=f.params)
                for f in scored.factors
                if f.factor == "rotation"
            ),
            None,
        ),
        calendar=api.CropCalendar(
            sowing_window=api.DateWindow(start=sow_start, end=sow_end),
            harvest_window=api.DateWindow(start=harvest_start, end=harvest_end),
            duration_days=crop.duration_days,
            days_until_sowing=schedule.days_until_sowing,
            window_status=schedule.window_status,
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
            input_cost_per_acre=result.input_cost_per_acre,
            margin_per_acre=result.margin_per_acre,
            expected_yield_t_acre=result.expected_yield_t_acre,
        ),
        attribution=[
            api.Attribution(
                factor=row.factor,
                contribution=row.contribution,
                headroom=row.headroom,
                score=row.score,
                impact=row.impact,
                detail=row.detail,
                code=row.code,
                params=row.params,
            )
            for row in attribute(scored)
        ],
        counterfactuals=[
            api.Counterfactual(
                factor=item.factor,
                kind=item.kind,
                current_value=item.current_value,
                target_value=item.target_value,
                score_gain=item.score_gain,
                rank_gain=item.rank_gain,
                message=item.message,
                params=item.params,
            )
            for item in (counterfactuals or [])
        ],
        price_outlook=api.PriceOutlook(
            harvest_month=outlook.harvest_month,
            expected_per_quintal=outlook.expected_per_quintal,
            low_per_quintal=outlook.low_per_quintal,
            high_per_quintal=outlook.high_per_quintal,
            msp_floor_per_quintal=outlook.msp_floor_per_quintal,
            current_per_quintal=outlook.current_per_quintal,
            basis=outlook.basis,
            observations_used=outlook.observations_used,
            explanation=outlook.explanation,
            explanation_code=outlook.explanation_code,
            explanation_params=outlook.explanation_params,
            below_msp_by=outlook.below_msp_by,
        ),
        risks=[
            api.Risk(type=risk.type, name=risk.name, severity=risk.severity)
            for risk in crop.risks
        ],
    )


def _build_risk_plan(
    recommendations: Sequence[api.Recommendation],
    *,
    reference: ReferenceData,
    area_ha: float,
    irrigation: str,
    priced_codes: set[str],
    water_status: dict[str, str] | None = None,
) -> api.RiskPlan:
    """Translate the ranked list into the diversification service's vocabulary."""
    ranked_specs = [
        (
            reference.crops[item.crop_code],
            item.score,
            item.economics.margin_per_ha,
        )
        for item in recommendations
        if item.crop_code in reference.crops
    ]

    result = diversification.build(
        ranked_specs,
        area_ha=area_ha,
        irrigation=irrigation,
        priced_codes=priced_codes,
        water_status=water_status,
    )

    return api.RiskPlan(
        exposures=[
            api.RiskExposure(
                crop_code=exposure.crop_code,
                name=exposure.name,
                agronomic=exposure.agronomic,
                price=exposure.price,
                water=exposure.water,
                risk_types=list(exposure.risk_types),
                severe_risks=list(exposure.severe_risks),
                drivers=list(exposure.drivers),
            )
            for exposure in result.exposures
        ],
        plan=[
            api.Allocation(
                crop_code=allocation.crop_code,
                name=allocation.name,
                share=allocation.share,
                area_ha=allocation.area_ha,
                net_margin=allocation.net_margin,
            )
            for allocation in result.plan
        ],
        overlap=result.overlap,
        combined_margin=result.combined_margin,
        single_crop_margin=result.single_crop_margin,
        single_crop_name=result.single_crop_name,
        single_crop_code=result.single_crop_code,
        margin_given_up=result.margin_given_up,
        verdict_code=result.verdict_code,
        verdict_params=result.verdict_params,
    )


def recommend(
    request: api.RecommendationRequest,
    reference: ReferenceData,
    *,
    request_id: str | None = None,
    today: date | None = None,
    repository: object | None = None,
) -> api.RecommendationResponse:
    request_id = request_id or new_request_id()
    today = today or datetime.now(timezone.utc).date()

    # 1. Where is this field?
    place = resolve_place(request.location, request.area_ha)

    # 2. What are its conditions? Never raises - degrades instead.
    conditions = get_conditions(place, request.season)

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
        previous_crop=request.previous_crop,
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
    from apps.api.core.price_history import PriceHistory
    from apps.api.core.repository import DEFAULT_SQLITE_PATH
    import os

    try:
        history = PriceHistory(Path(os.getenv("RESULTS_DB_PATH", "") or DEFAULT_SQLITE_PATH))
    except Exception:
        logger.warning("Price history unavailable; outlook falls back to MSP", exc_info=True)
        history = None

    price_service = PriceService(reference, history=history)
    recommendations: list[api.Recommendation] = []
    unpriced: list[tuple[str, str]] = []

    ranker = RulesRanker()
    ml_constraints = Constraints(
        exclude_crops=tuple(request.constraints.exclude_crops),
        max_input_cost=request.constraints.max_input_cost,
        organic_only=request.constraints.organic_only,
    )

    for position, scored in enumerate(top, start=1):
        crop = reference.crops[scored.crop_code]

        # Pure computation over a handful of factors — no I/O, microseconds.
        try:
            crop_counterfactuals = find_counterfactuals(
                ranker, ranking_input, candidates, ml_constraints, scored.crop_code
            )
        except Exception:
            logger.exception("Counterfactuals failed for %s", scored.crop_code)
            crop_counterfactuals = []

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
            counterfactuals=crop_counterfactuals,
        )
        if recommendation.economics.expected_price_per_quintal is None:
            unpriced.append((crop.crop_code, crop.name))
        recommendations.append(recommendation)

    # A second ordering: by money rather than by fit.
    #
    # Sorted here rather than in the browser. It is only a sort of figures that
    # already exist, but "which crop earns most" is a claim about money, and
    # every claim about money in this app is made in one place.
    _priced = [
        item
        for item in recommendations
        if item.economics.net_margin is not None
    ]
    _priced.sort(key=lambda item: item.economics.net_margin, reverse=True)
    for _position, _item in enumerate(_priced, start=1):
        _item.rank_by_return = _position

    # Water first: the risk panel derives its water exposure from these
    # budgets, so the two cannot end up describing the same field differently.
    water_budgets: list[api.WaterBudget] = []
    try:
        for item in recommendations:
            crop = reference.crops.get(item.crop_code)
            if crop is None:
                continue
            budget = water_module.build(
                crop,
                season_rainfall_mm=conditions.weather.season_rainfall_mm,
                area_ha=place.area_ha,
                irrigation=request.irrigation,
            )
            water_budgets.append(
                api.WaterBudget(
                    crop_code=budget.crop_code,
                    name=budget.name,
                    requirement_mm=budget.requirement_mm,
                    comfortable_mm=budget.comfortable_mm,
                    season_rainfall_mm=budget.season_rainfall_mm,
                    effective_rainfall_mm=budget.effective_rainfall_mm,
                    deficit_mm=budget.deficit_mm,
                    deficit_m3=budget.deficit_m3,
                    waterings=budget.waterings,
                    waterings_comfortable=budget.waterings_comfortable,
                    deficit_comfortable_mm=budget.deficit_comfortable_mm,
                    surplus_mm=budget.surplus_mm,
                    status=budget.status,
                    can_be_met=budget.can_be_met,
                )
            )
    except Exception:
        logger.exception("Water budget failed; continuing without it")

    # District crowding. Two real signals, and no invented aggregate: see
    # services/crowding.py for why the obvious version of this feature cannot
    # be built honestly.
    crowding_rows: list[api.Crowding] = []
    try:
        # `advisories_total` deliberately EXCLUDES the advisory being generated
        # right now — it has not been saved yet. Counting it would make every
        # farmer the +1 that tipped their own district, and the total on screen
        # would never match the total in the store.
        counts, total, seeded_total = ({}, 0, 0)
        if repository is not None:
            counts, total, seeded_total = repository.top_crop_counts(
                place.district_code, request.season
            )

        for item in recommendations:
            harvest_month = (
                item.calendar.harvest_window.start.month
                if item.calendar and item.calendar.harvest_window
                else None
            )
            harvest_prices, other_prices, scope = ([], [], "none")
            if history is not None and harvest_month is not None:
                harvest_prices, other_prices, scope = history.harvest_month_comparison(
                    item.crop_code, harvest_month, place.district_code
                )

            signal = crowding_module.build(
                item.crop_code,
                times_ranked_first=counts.get(item.crop_code, 0),
                advisories_total=total,
                harvest_month=harvest_month,
                harvest_month_prices=harvest_prices,
                other_month_prices=other_prices,
                price_scope=scope,
                seeded_advisories=seeded_total,
            )
            crowding_rows.append(
                api.Crowding(
                    crop_code=signal.crop_code,
                    name=item.name,
                    concentration=api.AdviceConcentration(
                        crop_code=signal.concentration.crop_code,
                        times_ranked_first=signal.concentration.times_ranked_first,
                        advisories_total=signal.concentration.advisories_total,
                        share=signal.concentration.share,
                        band=signal.concentration.band,
                        code=signal.concentration.code,
                        params=signal.concentration.params,
                    ),
                    dip=api.HarvestDip(
                        crop_code=signal.dip.crop_code,
                        harvest_month=signal.dip.harvest_month,
                        harvest_median=signal.dip.harvest_median,
                        other_median=signal.dip.other_median,
                        dip_fraction=signal.dip.dip_fraction,
                        band=signal.dip.band,
                        observations=signal.dip.observations,
                        scope=signal.dip.scope,
                        code=signal.dip.code,
                        params=signal.dip.params,
                    ),
                    caveat_codes=signal.caveat_codes,
                    seeded_advisories=signal.seeded_advisories,
                )
            )
    except Exception:
        logger.exception("Crowding signal failed; continuing without it")

    # Exposure, and whether splitting the field would actually reduce it.
    # Uses the recommendations already built, so the money in any split plan is
    # derived from the same economics as everything else on the page.
    risk_plan = None
    try:
        priced_codes = {
            item.crop_code
            for item in recommendations
            if item.economics.expected_price_per_quintal is not None
        }
        risk_plan = _build_risk_plan(
            recommendations,
            reference=reference,
            area_ha=place.area_ha,
            irrigation=request.irrigation,
            priced_codes=priced_codes,
            water_status={b.crop_code: b.status for b in water_budgets},
        )
    except Exception:
        # A missing risk panel is a smaller failure than a missing answer.
        # architecture.md principle 2: degrade, never collapse.
        logger.exception("Risk plan failed; returning recommendations without it")

    # Last season's crop, valued the same way. Scored even when it falls outside
    # the top N, because a farmer comparing against their own choice needs it
    # ranked honestly rather than omitted.
    comparison = None
    if request.previous_crop:
        previous_code = request.previous_crop.upper()
        previous_spec = reference.crops.get(previous_code)

        if previous_spec is None:
            logger.info("Unknown previous_crop %r; skipping comparison", previous_code)
        elif recommendations:
            previous_scored = next(
                (item for item in ranked if item.crop_code == previous_code), None
            )
            previous_recommendation = None

            if previous_scored is not None:
                previous_rank = (
                    next(
                        index
                        for index, item in enumerate(ranked, start=1)
                        if item.crop_code == previous_code
                    )
                )
                previous_recommendation = _build_recommendation(
                    rank=previous_rank,
                    scored=previous_scored,
                    crop=previous_spec,
                    ranking_input=ranking_input,
                    area_ha=place.area_ha,
                    price_service=price_service,
                    district_code=place.district_code,
                    today=today,
                    sowing_date=request.sowing_date,
                )

            comparison = build_comparison(
                previous_recommendation,
                previous_code,
                previous_spec.name,
                recommendations[0],
            )

    return api.RecommendationResponse(
        request_id=request_id,
        generated_at=datetime.now(timezone.utc),
        location_resolved=api.ResolvedLocation(
            state_code=place.state_code,
            district_code=place.district_code,
            district_name=place.district_name,
            centroid=list(place.centroid),
            area_ha=place.area_ha,
            area_acres=round(place.area_ha * economics_module.ACRES_PER_HECTARE, 2),
            precision=place.precision,
        ),
        conditions=_conditions_to_api(conditions),
        recommendations=recommendations,
        risk=risk_plan,
        water=water_budgets,
        crowding=crowding_rows,
        request_echo=api.RequestEcho(
            location=request.location,
            season=request.season,
            area_ha=request.area_ha,
            irrigation=request.irrigation,
            soil_test=request.soil_test,
            previous_crop=request.previous_crop,
        ),
        comparison=comparison,
        warnings=_collect_warnings(
            conditions,
            reference,
            unpriced,
            # Keyed to the TOP recommendation, because that is the one a farmer
            # will act on. Requiring every crop to have missed its window was too
            # strict: one outlier with a late window (onion sows in November and
            # is listed under kharif) suppressed the banner for a season whose
            # main sowing had plainly closed.
            closed_season=(
                request.season
                if recommendations
                and recommendations[0].calendar.window_status == "closed_this_year"
                else None
            ),
        ),
    )


def _crop_history(history) -> api.CropHistory | None:
    """Read cropping intensity off the NDVI series already fetched.

    Free: the history is retrieved for the chart regardless, so this costs one
    pass over 24 numbers and no extra Earth Engine call. Failure returns None
    rather than taking the map panel down with it.
    """
    if not history:
        return None

    try:
        analysis = analyse_crop_history(
            [(point.date.isoformat(), point.ndvi) for point in history]
        )
    except Exception:
        logger.exception("Crop history analysis failed; omitting it")
        return None

    return api.CropHistory(
        intensity=analysis.intensity,
        cycles=[
            api.CropCycle(
                peak_month=cycle.peak_month,
                peak_ndvi=cycle.peak_ndvi,
                season=cycle.season,
                start_month=cycle.start_month,
                end_month=cycle.end_month,
                months=cycle.months,
            )
            for cycle in analysis.cycles
        ],
        cycles_per_year=analysis.cycles_per_year,
        seasons_used=list(analysis.seasons_used),
        fallow_months=analysis.fallow_months,
        observed_months=analysis.observed_months,
        total_months=analysis.total_months,
        season_coverage=analysis.season_coverage,
        confidence=analysis.confidence,
        caveat_codes=list(analysis.caveat_codes),
    )


def _productivity(result, history=None) -> api.Productivity | None:
    """Interpret the raw amplitude sample. Never takes the panel down.

    `history` is this plot's crop-history reading. The two panels describe the
    same field and must not contradict each other: ranking a plot that grew
    nothing tells a farmer they are in the 17th percentile when the finding is
    that there was no crop there at all.
    """
    sample = getattr(result, "productivity", None)
    if sample is None:
        return None

    try:
        observed = [p.ndvi for p in result.history if p.ndvi is not None]
        coverage = len(observed) / max(len(result.history), 1)

        analysis = analyse_productivity(
            sample.plot_amplitude,
            sample.percentiles or {},
            neighbourhood_km=sample.neighbourhood_km,
            sample_pixels=sample.sample_pixels,
            season_coverage=coverage,
            crop_detected=(
                history is None
                or history.intensity not in ("uncropped", "fallow", "unknown")
            ),
        )
    except Exception:
        logger.exception("Productivity analysis failed; omitting it")
        return None

    return api.Productivity(
        plot_amplitude=analysis.plot_amplitude,
        percentile=analysis.percentile,
        band=analysis.band,
        percentiles={str(k): v for k, v in analysis.percentiles.items()},
        neighbourhood_km=analysis.neighbourhood_km,
        sample_pixels=analysis.sample_pixels,
        caveat_codes=list(analysis.caveat_codes),
    )


def build_indices(location: api.Location, area_ha: float = 1.0) -> api.IndicesResponse:
    """Spectral indices for a location, for the map overlay and history chart."""
    from services.geo import get_indices

    place = resolve_place(location, area_ha)
    result = get_indices(place)

    history = _crop_history(result.history)

    return api.IndicesResponse(
        location_resolved=api.ResolvedLocation(
            state_code=place.state_code,
            district_code=place.district_code,
            district_name=place.district_name,
            centroid=list(place.centroid),
            area_ha=place.area_ha,
            precision=place.precision,
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
        crop_history=history,
        productivity=_productivity(result, history),
        source=result.source,
        tile_url_template=result.tile_url_template,
    )
