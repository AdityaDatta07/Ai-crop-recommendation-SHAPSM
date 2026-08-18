"""Factor scoring functions.

Every function here is pure: inputs in, a 0-1 score out, no I/O and no state.
That is what makes them unit-testable without a database, and it is why the
economics maths lives in apps/api rather than here.

Two different kinds of "we don't know", and they must not be conflated:

  Returning None means the FIELD data is missing - no soil test, no NDVI. That
  is a gap in our knowledge of this farm, it affects every candidate crop
  equally, and the caller drops the weight and renormalises. A missing
  measurement must never quietly score zero, or a crop would be marked down for
  the sin of sitting on an unsurveyed field.

  Returning a low score means the CROP data is missing - no notified support
  price, no published yield. That is a fact about the crop, not about the field,
  and it is real information: we cannot tell this farmer what they would earn.
  Renormalising it away would rank an unpriceable crop *higher*, which is
  backwards. It scores low and is flagged `estimated` so confidence drops too.
"""

from __future__ import annotations

# Inside the optimal band a crop still scores better nearer the middle of it.
# Without this every in-band crop ties on 1.0 and the ranking stops
# discriminating - six rabi crops landed within 0.04 of each other in testing,
# which is useless to a farmer choosing between them.
IN_BAND_FLOOR = 0.85

# What an unpriceable crop scores on market_price. Low, because "you may not be
# able to sell this predictably" is a genuine mark against a crop, but not zero,
# because plenty of farmers grow unpriced crops for good reasons.
UNPRICED_SCORE = 0.30


def taper(
    value: float,
    optimal: tuple[float, float],
    absolute: tuple[float, float],
    in_band_floor: float = IN_BAND_FLOOR,
) -> float:
    """Peaks at the centre of the optimal band, falls to 0.0 at the absolute limits.

                  1.0
        0.0     _-‾‾-_      0.0
      abs_lo  /        \\  abs_hi
        |____/          \\____|
           opt_lo    opt_hi
           (0.85)     (0.85)

    Inside the optimal band the score runs from `in_band_floor` at the edges to
    1.0 dead centre. Outside it, a straight taper to zero at the absolute limit.
    The two halves meet at `in_band_floor`, so the curve is continuous.
    """
    abs_lo, abs_hi = absolute
    opt_lo, opt_hi = optimal

    if value < abs_lo or value > abs_hi:
        return 0.0

    if opt_lo <= value <= opt_hi:
        half_width = (opt_hi - opt_lo) / 2.0
        if half_width <= 0:
            return 1.0
        centre = (opt_lo + opt_hi) / 2.0
        closeness = 1.0 - abs(value - centre) / half_width  # 1.0 centre, 0.0 edge
        return in_band_floor + (1.0 - in_band_floor) * closeness

    if value < opt_lo:
        span = opt_lo - abs_lo
        return in_band_floor * ((value - abs_lo) / span) if span > 0 else 0.0

    span = abs_hi - opt_hi
    return in_band_floor * ((abs_hi - value) / span) if span > 0 else 0.0


def score_ph(ph: float | None, optimal: tuple[float, float], absolute: tuple[float, float]) -> float | None:
    if ph is None:
        return None
    return taper(ph, optimal, absolute)


def score_temperature(
    temp_c: float | None, optimal: tuple[float, float], absolute: tuple[float, float]
) -> float | None:
    if temp_c is None:
        return None
    return taper(temp_c, optimal, absolute)


def score_texture(texture: str | None, preferred: tuple[str, ...]) -> float | None:
    """Exact match scores 1.0; a shared component scores 0.6; anything else 0.35.

    Not zero for a mismatch: wheat on sand is a poor idea, not an impossible one,
    and the farmer may have no other land.
    """
    if texture is None:
        return None

    normalised = texture.strip().lower()
    preferred_lower = [p.lower() for p in preferred]

    if normalised in preferred_lower:
        return 1.0

    words = set(normalised.split())
    if any(words & set(p.split()) for p in preferred_lower):
        return 0.6
    return 0.35


# Indicative available-nitrogen bands in kg/ha. Provisional, like everything
# else derived from crops.yaml.
NITROGEN_BANDS = {"low": 140.0, "medium": 220.0, "high": 300.0}


def score_nitrogen(
    nitrogen_kg_ha: float | None, demand: str, legume: bool
) -> float | None:
    """Legumes fix their own nitrogen, so soil N barely constrains them."""
    if legume:
        return 1.0
    if nitrogen_kg_ha is None:
        return None

    required = NITROGEN_BANDS.get(demand, NITROGEN_BANDS["medium"])
    ratio = nitrogen_kg_ha / required
    if ratio >= 1.0:
        return 1.0
    # A deficit is correctable with fertiliser, so the floor is 0.3 rather than 0.
    return max(0.3, ratio)


IRRIGATION_CAPACITY = {"rainfed": 0.0, "canal": 0.6, "tubewell": 0.85, "drip": 1.0}
IRRIGATION_NEED_MM = {"low": 100.0, "medium": 250.0, "high": 500.0}


def score_rainfall(
    season_rainfall_mm: float | None,
    required_mm: tuple[float, float],
    irrigation: str,
) -> float | None:
    """Does rainfall plus the farmer's irrigation cover what the crop needs?

    Surplus is not a bonus. Beyond the upper bound the score falls again -
    waterlogging is a real failure mode, not a free win.
    """
    if season_rainfall_mm is None:
        return None

    low, high = required_mm
    capacity = IRRIGATION_CAPACITY.get(irrigation, 0.0)

    # Irrigation can make up a shortfall, scaled by how much control it gives.
    # It cannot take water away, so a surplus is left alone.
    if season_rainfall_mm < low:
        shortfall = low - season_rainfall_mm
        effective = season_rainfall_mm + shortfall * capacity
    else:
        effective = season_rainfall_mm

    if low <= effective <= high:
        return 1.0
    if effective < low:
        return max(0.0, effective / low) if low > 0 else 0.0
    # Excess: tolerate 50% over the upper bound before scoring zero.
    overshoot = (effective - high) / (high * 0.5) if high > 0 else 1.0
    return max(0.0, 1.0 - overshoot)


# How much SUPPLEMENTAL water a crop needs beyond rainfall, 0-1. Low-need crops
# sit at 0.0 because rain alone can carry them - that is the whole point of a
# drought-tolerant crop, and rainfed land must not be penalised for choosing one.
SUPPLEMENTAL_NEED = {"low": 0.0, "medium": 0.45, "high": 0.85}

# A shortfall here is a warning, not a veto. Whether the water actually balances
# is the rainfall factor's job, and it carries nearly twice the weight. Rainfed
# rice in a 1500 mm district is normal; this factor must not rule it out.
IRRIGATION_FLOOR = 0.30


def score_irrigation(irrigation: str, need: str) -> float:
    """Can this water source meet the crop's need for water beyond rainfall?

    Deliberately not a veto. Scores 1.0 whenever the source covers the
    supplemental requirement - including rainfed land growing a low-water crop,
    which is the single most common case among the farmers this tool is for.
    """
    capacity = IRRIGATION_CAPACITY.get(irrigation, 0.0)
    required = SUPPLEMENTAL_NEED.get(need, SUPPLEMENTAL_NEED["medium"])

    if required <= 0 or capacity >= required:
        return 1.0
    return IRRIGATION_FLOOR + (1.0 - IRRIGATION_FLOOR) * (capacity / required)


def score_market(
    price_per_quintal: int | None,
    cost_per_quintal: int | None,
) -> float:
    """Margin per unit as a proxy for market attractiveness.

    Ratio-based rather than absolute so a cheap crop with a good margin is not
    beaten by an expensive one with a thin one. Capped at a 100% margin, beyond
    which more upside stops moving the ranking - this factor is only weighted
    0.10 and should not be able to dominate agronomy.

    Never returns None. An unpriceable crop is a *known* unknown, so it takes
    the UNPRICED_SCORE penalty rather than having its weight renormalised away.
    See the module docstring for why that distinction matters.
    """
    if price_per_quintal is None or cost_per_quintal is None or cost_per_quintal <= 0:
        return UNPRICED_SCORE

    margin_ratio = (price_per_quintal - cost_per_quintal) / cost_per_quintal
    return max(0.0, min(1.0, margin_ratio))


def is_priced(price_per_quintal: int | None, cost_per_quintal: int | None) -> bool:
    """Whether score_market had real figures to work with.

    Drives the `estimated` flag on the factor, which keeps the penalty out of
    the confidence calculation's numerator - we are less sure about this crop,
    not more.
    """
    return not (price_per_quintal is None or cost_per_quintal is None or cost_per_quintal <= 0)
