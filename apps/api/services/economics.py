"""Cost, revenue and margin.

This is the ONLY place in the system where money is calculated. The frontend
displays what this returns and does no arithmetic, which means there is exactly
one place a wrong number can come from. Keep it that way.

Every function returns None rather than a zero or a guess when an input is
missing. `None` reaches the screen as an em dash; a zero would be a lie.

Units, stated once because mixing them is how these bugs happen:
    yield   tonnes per hectare
    price   rupees per quintal      (1 tonne = 10 quintals)
    cost    rupees per hectare
    area    hectares
    money   integer rupees, no paise
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

QUINTALS_PER_TONNE = 10

# 1 hectare = 10,000 m^2; 1 acre = 4,046.8564224 m^2 (international acre).
ACRES_PER_HECTARE = 2.4710538147


@dataclass(frozen=True)
class EconomicsResult:
    expected_yield_t_ha: float | None
    input_cost_per_ha: int | None
    expected_price_per_quintal: int | None
    gross_revenue: int | None
    net_margin: int | None
    margin_per_ha: int | None
    price_source: str | None
    price_as_of: date | None

    # Same figures, the unit most Indian farmers actually use.
    input_cost_per_acre: int | None = None
    margin_per_acre: int | None = None
    expected_yield_t_acre: float | None = None


def input_cost_per_ha(
    cost_a2fl_per_quintal: int | None,
    published_yield_kg_per_ha: float | None,
) -> int | None:
    """Derive cost per hectare from the published cost per quintal.

    CACP publishes A2+FL per quintal, not per hectare, so this multiplies by the
    yield the cost was assessed against - the PUBLISHED average, deliberately,
    not our adjusted forecast. Using the adjusted figure would make a field with
    good conditions look more expensive to farm, which is backwards.
    """
    if cost_a2fl_per_quintal is None or published_yield_kg_per_ha is None:
        return None
    quintals_per_ha = published_yield_kg_per_ha / 100.0
    return round(cost_a2fl_per_quintal * quintals_per_ha)


def compute(
    *,
    expected_yield_t_ha: float | None,
    published_yield_kg_per_ha: float | None,
    cost_a2fl_per_quintal: int | None,
    price_per_quintal: int | None,
    area_ha: float,
    price_source: str | None,
    price_as_of: date | None,
) -> EconomicsResult:
    """Full economics for one crop on one plot.

    Degrades field by field: no price still yields a cost, and the agronomic
    advice stands on its own. architecture.md principle 2.
    """
    cost_per_ha = input_cost_per_ha(cost_a2fl_per_quintal, published_yield_kg_per_ha)

    gross: int | None = None
    if expected_yield_t_ha is not None and price_per_quintal is not None:
        total_quintals = expected_yield_t_ha * area_ha * QUINTALS_PER_TONNE
        gross = round(total_quintals * price_per_quintal)

    net: int | None = None
    margin_per_ha: int | None = None
    if gross is not None and cost_per_ha is not None:
        net = round(gross - cost_per_ha * area_ha)
        margin_per_ha = round(net / area_ha) if area_ha > 0 else None

    return EconomicsResult(
        expected_yield_t_ha=expected_yield_t_ha,
        input_cost_per_ha=cost_per_ha,
        input_cost_per_acre=(
            round(cost_per_ha / ACRES_PER_HECTARE) if cost_per_ha is not None else None
        ),
        margin_per_acre=(
            round(margin_per_ha / ACRES_PER_HECTARE) if margin_per_ha is not None else None
        ),
        expected_yield_t_acre=(
            round(expected_yield_t_ha / ACRES_PER_HECTARE, 3)
            if expected_yield_t_ha is not None
            else None
        ),
        expected_price_per_quintal=price_per_quintal,
        gross_revenue=gross,
        net_margin=net,
        margin_per_ha=margin_per_ha,
        # Only claim a price source when there is actually a price.
        price_source=price_source if price_per_quintal is not None else None,
        price_as_of=price_as_of if price_per_quintal is not None else None,
    )
