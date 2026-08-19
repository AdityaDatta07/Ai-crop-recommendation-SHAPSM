"""Risk exposure, and whether splitting the field actually reduces it.

WHAT THIS IS NOT
----------------
It is not a portfolio optimiser. A real one needs the covariance of crop
returns across seasons, and we do not have that — nobody has it at district
resolution for Indian smallholdings, and inventing a correlation matrix to make
the output look quantitative would be the single most dishonest thing in this
codebase.

WHAT IT IS INSTEAD
------------------
Three exposures we can point at a source for:

  agronomic  the crop's own pest, disease and weather risks from crops.yaml
  price      whether an MSP floor exists, or the crop is fully market-exposed
  water      the crop's irrigation need against the water the farmer reported

And one idea that does the real work: **two crops only diversify each other if
they fail for different reasons.** Splitting a field between two crops that both
succumb to pod borer, both lack a support price, and both need water the farmer
does not have is not diversification. It is the same bet, twice.

So the split is chosen by minimising overlap, and when no low-overlap partner
exists we say so rather than manufacturing a plan. "Every crop that suits this
field this season carries the same risk" is a real finding and worth telling a
farmer, even though it is not the answer they hoped for.

The percentages are a stated rule of thumb, not an optimum, and the API says so
in the text it returns. Diversifying usually costs expected margin — that is
what it buys safety with — and the response reports that cost rather than
hiding it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Sequence

from services.ml.types import CropSpec

Level = Literal["low", "medium", "high"]

# --------------------------------------------------------------------- tuning

SEVERITY_WEIGHT = {"low": 1.0, "medium": 2.0, "high": 3.0}

AGRONOMIC_HIGH = 5.0
AGRONOMIC_MEDIUM = 3.0

#: Below this the second crop is a strip, not a plot. Splitting half an acre
#: three ways costs more in seed, labour and attention than the risk it spreads.
MIN_SPLIT_AREA_HA = 0.4

#: A partner must be genuinely suitable. Diversifying into a crop that does not
#: suit the field trades one risk for a larger one.
MIN_PARTNER_SCORE_RATIO = 0.75

#: Above this the two crops fail together often enough that the split is
#: theatre. Tuned so sharing one risk type of three is still worth doing.
MAX_USEFUL_OVERLAP = 0.6

#: The partner never takes the majority: the top crop is the best fit and the
#: split is a hedge against it, not a vote of no confidence in it.
MIN_PARTNER_SHARE = 0.25
MAX_PARTNER_SHARE = 0.40

#: Risk types that a farmer can do nothing about once sown, so two crops
#: sharing one are genuinely correlated rather than merely similar.
CORRELATED_TYPES = {"weather", "resource", "market"}


@dataclass(frozen=True)
class Exposure:
    """One crop's risk, on three axes we can source."""

    crop_code: str
    name: str
    agronomic: Level
    price: Level
    water: Level
    risk_types: tuple[str, ...]
    severe_risks: tuple[str, ...]
    """The high-severity risks by name, so the UI can say "pod borer"."""

    drivers: tuple[str, ...]
    """Message codes naming what drives the exposure. Localised client-side."""


@dataclass(frozen=True)
class Allocation:
    crop_code: str
    name: str
    share: float
    """0..1 of the field."""

    area_ha: float
    net_margin: int | None


@dataclass(frozen=True)
class Diversification:
    exposures: tuple[Exposure, ...]
    plan: tuple[Allocation, ...] = ()
    overlap: float | None = None
    combined_margin: int | None = None

    single_crop_margin: int | None = None
    """The best a SINGLE crop could earn on this field — not the top-ranked one.

    These differ, and the difference matters. Ranking is by agronomic fit, so
    the crop at rank 1 can earn far less per hectare than one below it. An
    earlier version compared the split against rank 1 only and reported that
    splitting "earns more than a single crop" — while planting all of the
    second crop would have beaten the split by more still. That is a false
    statement about a farmer's money, which is the worst thing this codebase
    could say.
    """

    single_crop_name: str = ""
    single_crop_code: str = ""

    margin_given_up: int | None = None
    """single_crop_margin - combined_margin. What the hedge costs.

    Positive nearly always: spreading risk is paid for in expected margin.
    Negative only when the split genuinely beats every single-crop option.
    """
    verdict_code: str = ""
    verdict_params: dict = field(default_factory=dict)


# ------------------------------------------------------------------ exposures


def _agronomic(crop: CropSpec) -> tuple[Level, tuple[str, ...]]:
    total = sum(SEVERITY_WEIGHT.get(risk.severity, 1.0) for risk in crop.risks)
    severe = tuple(risk.name for risk in crop.risks if risk.severity == "high")

    if total >= AGRONOMIC_HIGH:
        return "high", severe
    if total >= AGRONOMIC_MEDIUM:
        return "medium", severe
    return "low", severe


def _price(crop: CropSpec, has_market_price: bool) -> Level:
    """An MSP floor is the only thing that bounds the downside.

    Note this is exposure, not expected earnings. A crop can be highly
    profitable and still fully exposed — that is precisely the combination
    worth flagging before a farmer puts the whole field into it.
    """
    if crop.price_per_quintal is not None:
        return "low"
    return "medium" if has_market_price else "high"


def _water(crop: CropSpec, irrigation: str, water_status: str | None) -> Level:
    """Derived from the water budget when we have one.

    Two panels on the same page describing the same thing must not disagree.
    Before this, the risk table read water exposure off the crop's `irrigation
    need` category while the water budget worked from actual millimetres — so a
    crop could show "Low" exposure beside a budget saying its need cannot be
    met. The budget is the better measurement, so it wins; the category is only
    a fallback for when rainfall is unavailable.
    """
    if water_status == "cannot_meet":
        return "high"
    if water_status == "needs_irrigation":
        return "medium"
    if water_status in ("rain_sufficient", "surplus"):
        return "low"

    if irrigation != "rainfed":
        return "low"
    if crop.irrigation_need == "high":
        return "high"
    if crop.irrigation_need == "medium":
        return "medium"
    return "low"


def assess(
    crop: CropSpec,
    *,
    irrigation: str,
    has_market_price: bool,
    water_status: str | None = None,
) -> Exposure:
    agronomic, severe = _agronomic(crop)
    price = _price(crop, has_market_price)
    water = _water(crop, irrigation, water_status)

    drivers: list[str] = []
    # Every non-low level must produce a sentence. Otherwise a crop badged
    # "Medium" sat next to the words "nothing standing out", and the reader has
    # to decide which of the two to believe.
    if agronomic == "high":
        drivers.append("severe_pest_or_disease")
    elif agronomic == "medium":
        drivers.append("moderate_pest_or_disease")
    if price == "high":
        drivers.append("no_price_floor")
    elif price == "medium":
        drivers.append("market_priced_only")
    if water == "high":
        drivers.append("thirsty_and_rainfed")
    elif water == "medium":
        drivers.append("some_water_dependence")
    if not drivers:
        drivers.append("nothing_notable")

    return Exposure(
        crop_code=crop.crop_code,
        name=crop.name,
        agronomic=agronomic,
        price=price,
        water=water,
        risk_types=tuple(sorted({risk.type for risk in crop.risks})),
        severe_risks=severe,
        drivers=tuple(drivers),
    )


# -------------------------------------------------------------------- overlap


def overlap(a: Exposure, b: Exposure) -> float:
    """How much two crops fail for the same reasons. 0 = independent, 1 = twins.

    Deliberately crude and deliberately explainable. Every term below is
    something a farmer would recognise as a shared fate, and the whole thing
    could be recomputed on paper.
    """
    terms: list[float] = []

    shared = set(a.risk_types) & set(b.risk_types)
    union = set(a.risk_types) | set(b.risk_types)
    if union:
        # Weather and market hit both crops on the same day; a pest of one is
        # rarely a pest of the other. So shared uncontrollable types count
        # double before normalising.
        weight = sum(2.0 if kind in CORRELATED_TYPES else 1.0 for kind in shared)
        ceiling = sum(2.0 if kind in CORRELATED_TYPES else 1.0 for kind in union)
        terms.append(weight / ceiling)

    # Both unprotected on price means one bad mandi season takes the whole
    # field, however the agronomy went.
    terms.append(1.0 if a.price != "low" and b.price != "low" else 0.0)

    # Both thirsty on rainfed land means one failed monsoon takes both.
    terms.append(1.0 if a.water != "low" and b.water != "low" else 0.0)

    return round(sum(terms) / len(terms), 3) if terms else 0.0


def _worse_on_price(partner: Exposure, top: Exposure) -> bool:
    """True when the partner is more price-exposed than the crop it hedges."""
    order = {"low": 0, "medium": 1, "high": 2}
    return order[partner.price] > order[top.price]


# ----------------------------------------------------------------------- plan


def _share_for_partner(top_score: float, partner_score: float) -> float:
    """A stated rule, not an optimum — and the response says as much.

    Scaled by how close the partner is to the best crop, then bounded. The
    bounds matter more than the formula: the hedge should never be large enough
    to become the main bet, nor so small it is not worth the extra seed.
    """
    if top_score <= 0:
        return MIN_PARTNER_SHARE
    ratio = min(partner_score / top_score, 1.0)
    raw = MIN_PARTNER_SHARE + (MAX_PARTNER_SHARE - MIN_PARTNER_SHARE) * ratio
    return round(min(max(raw, MIN_PARTNER_SHARE), MAX_PARTNER_SHARE) * 20) / 20


def _margin_for(margin_per_ha: int | None, area_ha: float) -> int | None:
    return None if margin_per_ha is None else round(margin_per_ha * area_ha)


def build(
    ranked: Sequence[tuple[CropSpec, float, int | None]],
    *,
    area_ha: float,
    irrigation: str,
    priced_codes: set[str],
    water_status: dict[str, str] | None = None,
) -> Diversification:
    """`ranked` is (crop, score, margin_per_ha) in rank order, best first.

    margin_per_ha is a rate, so the combined figure is computed here — on the
    server, next to every other money calculation — and never in the browser.
    """
    if not ranked:
        return Diversification(exposures=(), verdict_code="no_crops")

    exposures = tuple(
        assess(
            crop,
            irrigation=irrigation,
            has_market_price=crop.crop_code in priced_codes,
            water_status=(water_status or {}).get(crop.crop_code),
        )
        for crop, _, _ in ranked
    )
    by_code = {exposure.crop_code: exposure for exposure in exposures}

    top_crop, top_score, top_margin_per_ha = ranked[0]
    top_exposure = by_code[top_crop.crop_code]

    # The baseline is the best single crop by MONEY, not by rank. See the note
    # on Diversification.single_crop_margin for why this distinction is not
    # pedantic.
    best_single = max(
        ((crop, margin) for crop, _, margin in ranked if margin is not None),
        key=lambda item: item[1],
        default=None,
    )
    single_crop_margin = (
        None if best_single is None else _margin_for(best_single[1], area_ha)
    )
    single_crop_name = "" if best_single is None else best_single[0].name
    single_crop_code = "" if best_single is None else best_single[0].crop_code

    if area_ha < MIN_SPLIT_AREA_HA:
        return Diversification(
            exposures=exposures,
            single_crop_margin=single_crop_margin,
            single_crop_name=single_crop_name,
            single_crop_code=single_crop_code,
            verdict_code="plot_too_small",
            verdict_params={"minimum": MIN_SPLIT_AREA_HA},
        )

    # Best partner = least shared fate, among crops that actually suit the field
    # AND are a genuine hedge. Two filters beyond suitability, both learned the
    # hard way from what this first produced:
    #
    #   priced   — the panel's claim is "you give up this much for safety". An
    #              unpriceable partner makes that figure null, and a plan whose
    #              cost cannot be stated is not a plan a farmer can weigh.
    #
    #   no worse — the first run offered onion beside pigeon pea. Onion carries
    #              no support price, so the "safer" split swapped a guaranteed
    #              floor on 40% of the field for none. Reducing one exposure by
    #              raising another is not diversification.
    candidates = [
        (crop, score, margin)
        for crop, score, margin in ranked[1:]
        if top_score > 0
        and score >= top_score * MIN_PARTNER_SCORE_RATIO
        and margin is not None
        and not _worse_on_price(by_code[crop.crop_code], top_exposure)
    ]
    if not candidates:
        return Diversification(
            exposures=exposures,
            single_crop_margin=single_crop_margin,
            single_crop_name=single_crop_name,
            single_crop_code=single_crop_code,
            verdict_code="no_suitable_partner",
            verdict_params={"crop": top_crop.name, "crop_code": top_crop.crop_code},
        )

    scored = sorted(
        (
            (overlap(top_exposure, by_code[crop.crop_code]), -score, crop, score, margin)
            for crop, score, margin in candidates
        ),
        key=lambda item: (item[0], item[1]),
    )
    best_overlap, _, partner, partner_score, partner_margin_per_ha = scored[0]

    if best_overlap > MAX_USEFUL_OVERLAP:
        # Worth saying plainly. A farmer who splits anyway has taken on the
        # cost of two crops for none of the protection.
        return Diversification(
            exposures=exposures,
            overlap=best_overlap,
            single_crop_margin=single_crop_margin,
            single_crop_name=single_crop_name,
            single_crop_code=single_crop_code,
            verdict_code="everything_shares_the_risk",
            verdict_params={
                "shared": ", ".join(
                    sorted(set(top_exposure.risk_types) & set(by_code[partner.crop_code].risk_types))
                )
                or "price and water exposure",
            },
        )

    partner_share = _share_for_partner(top_score, partner_score)
    top_share = round(1.0 - partner_share, 2)

    plan = (
        Allocation(
            crop_code=top_crop.crop_code,
            name=top_crop.name,
            share=top_share,
            area_ha=round(area_ha * top_share, 3),
            net_margin=_margin_for(top_margin_per_ha, area_ha * top_share),
        ),
        Allocation(
            crop_code=partner.crop_code,
            name=partner.name,
            share=partner_share,
            area_ha=round(area_ha * partner_share, 3),
            net_margin=_margin_for(partner_margin_per_ha, area_ha * partner_share),
        ),
    )

    parts = [allocation.net_margin for allocation in plan]
    combined = None if any(part is None for part in parts) else sum(parts)  # type: ignore[arg-type]

    given_up = (
        None
        if combined is None or single_crop_margin is None
        else single_crop_margin - combined
    )

    return Diversification(
        exposures=exposures,
        plan=plan,
        overlap=best_overlap,
        combined_margin=combined,
        single_crop_margin=single_crop_margin,
        single_crop_name=single_crop_name,
        single_crop_code=single_crop_code,
        margin_given_up=given_up,
        verdict_code="split_reduces_risk",
        verdict_params={
            "crop": top_crop.name,
            "crop_code": top_crop.crop_code,
            "partner": partner.name,
            "partner_code": partner.crop_code,
        },
    )
