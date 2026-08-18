"""Yield and price projection.

v1 uses published averages with a light seasonal adjustment. It returns None
rather than guessing when the history is not there - a null propagates to the
API as a null economics field and renders as a dash, which is honest. A
fabricated number would look identical to a real one on screen.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.ml.types import CropSpec, RankingInput


@dataclass(frozen=True)
class YieldForecast:
    """Expected yield in tonnes per hectare, with the basis stated."""

    t_per_ha: float | None
    basis: str


# How much of the published average a crop is expected to reach, given how well
# conditions suit it. Deliberately narrow: the published average already bakes in
# a spread of conditions, so a suitability score should nudge it, not double it.
MIN_MULTIPLIER = 0.70
MAX_MULTIPLIER = 1.15


def project_yield(
    crop: CropSpec,
    suitability_score: float,
    conditions: RankingInput,
) -> YieldForecast:
    """Scale the published average yield by how well this field suits the crop."""
    if crop.yield_kg_per_ha is None:
        return YieldForecast(
            t_per_ha=None,
            basis="No published yield figure for this crop.",
        )

    base_t_ha = crop.yield_kg_per_ha / 1000.0
    multiplier = MIN_MULTIPLIER + (MAX_MULTIPLIER - MIN_MULTIPLIER) * suitability_score

    # With poor input data the adjustment is guesswork, so fall back to the
    # unadjusted published average and say so.
    if conditions.data_completeness < 0.5:
        return YieldForecast(
            t_per_ha=round(base_t_ha, 2),
            basis="All-India average, unadjusted — too little field data to refine it.",
        )

    return YieldForecast(
        t_per_ha=round(base_t_ha * multiplier, 2),
        basis="All-India average, adjusted for how well this field suits the crop.",
    )


def project_price(crop: CropSpec) -> int | None:
    """The support price, where one is notified.

    This is the fallback. The price service overrides it with live mandi data
    when Agmarknet is reachable, because MSP is a floor with non-universal
    procurement, not what the farmer will actually be paid.
    """
    return crop.price_per_quintal
