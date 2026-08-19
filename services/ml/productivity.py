"""How vigorous this plot is compared with the land around it.

WHAT THE MEASURE IS
-------------------
NDVI amplitude: how far the canopy climbs between bare ground and peak growth
across one season. A field that goes 0.15 -> 0.75 has produced far more
biomass than one that goes 0.20 -> 0.40.

Amplitude rather than peak NDVI, deliberately. A mango orchard or a patch of
scrub sits high all year and would top a peak-NDVI ranking without ever growing
a crop. Amplitude measures the SWING, which is what a sown-and-harvested crop
does and permanent cover does not.

WHAT IT IS COMPARED AGAINST
---------------------------
Cropland within a radius of the plot, not the administrative district. Two
reasons: the reference data holds district centroids and no district polygons,
so "the district" is not a shape we can sample; and land a few kilometres away
shares this plot's soil, rainfall and market, which the far side of a large
district does not.

THREE THINGS THIS IS NOT
------------------------
It is not yield. Biomass and grain are related but not the same — a lush crop
that lodges before harvest scores well here and yields badly.

It is not a comparison of skill. The neighbours may be growing a different crop
entirely, and a pulse will never match a paddy for amplitude. Being "below
average" against a district of sugarcane means very little.

It is not a verdict on the farmer. Low amplitude can mean poor management, but
it can equally mean a deliberately low-input season, a fodder crop, or a
smallholding that simply is not irrigated. The panel says what was measured and
declines to explain why.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

Band = Literal["well_above", "above", "typical", "below", "well_below", "unknown"]

#: Percentile breakpoints we ask Earth Engine for. Five is enough to place a
#: value by interpolation without pulling a whole histogram over the wire.
PERCENTILES = (10, 25, 50, 75, 90)

#: Within this many percentile points of the middle, "typical" is the honest
#: word. Reporting a plot as "above average" for sitting on the 53rd percentile
#: implies a precision this measure does not have.
TYPICAL_MARGIN = 12

#: Below this many usable neighbourhood pixels the distribution is too thin to
#: compare against — a handful of fields is not a benchmark.
MIN_NEIGHBOURHOOD_PIXELS = 200


@dataclass(frozen=True)
class Productivity:
    plot_amplitude: float | None
    """Peak minus trough NDVI for this plot, this season."""

    percentiles: dict
    """Neighbourhood amplitude at each breakpoint in PERCENTILES."""

    percentile: int | None
    """Where the plot falls in that distribution, 0-100."""

    band: Band
    neighbourhood_km: float
    sample_pixels: int
    caveat_codes: tuple[str, ...]


def _percentile_of(value: float, percentiles: dict) -> int | None:
    """Place a value in a distribution described by a few breakpoints.

    Linear interpolation between the breakpoints either side. Values beyond the
    outermost breakpoints are clamped rather than extrapolated: we know the plot
    is above the 90th, and pretending to know it is at the 97th would be
    inventing precision from a distribution we only sampled five points of.
    """
    known = sorted((int(k), v) for k, v in percentiles.items() if v is not None)
    if len(known) < 2:
        return None

    if value <= known[0][1]:
        return known[0][0]
    if value >= known[-1][1]:
        return known[-1][0]

    for (low_pct, low_val), (high_pct, high_val) in zip(known, known[1:]):
        if low_val <= value <= high_val:
            if high_val == low_val:
                return low_pct
            fraction = (value - low_val) / (high_val - low_val)
            return round(low_pct + fraction * (high_pct - low_pct))

    return None


def _band_for(percentile: int | None) -> Band:
    if percentile is None:
        return "unknown"
    if abs(percentile - 50) <= TYPICAL_MARGIN:
        return "typical"
    if percentile >= 75:
        return "well_above"
    if percentile > 50:
        return "above"
    if percentile <= 25:
        return "well_below"
    return "below"


def analyse(
    plot_amplitude: float | None,
    percentiles: dict,
    *,
    neighbourhood_km: float,
    sample_pixels: int,
    season_coverage: float = 1.0,
    crop_detected: bool = True,
) -> Productivity:
    """Place this plot's amplitude in the neighbourhood distribution.

    `crop_detected` comes from the crop-history reading of the same plot. When
    that says nothing was grown, this must not report a percentile: "well below
    the land around it" reads as a verdict on the farmer, when the actual
    finding is that there is no crop here to judge — bare ground, an orchard,
    or a boundary drawn over something that is not a field.
    """
    caveats: list[str] = []

    if not crop_detected:
        return Productivity(
            plot_amplitude=round(plot_amplitude, 3) if plot_amplitude is not None else None,
            percentiles={int(k): round(v, 3) for k, v in (percentiles or {}).items() if v is not None},
            percentile=None,
            band="unknown",
            neighbourhood_km=neighbourhood_km,
            sample_pixels=sample_pixels,
            caveat_codes=("no_crop_to_compare",),
        )

    usable = {k: v for k, v in (percentiles or {}).items() if v is not None}

    if plot_amplitude is None or len(usable) < 2:
        return Productivity(
            plot_amplitude=plot_amplitude,
            percentiles=usable,
            percentile=None,
            band="unknown",
            neighbourhood_km=neighbourhood_km,
            sample_pixels=sample_pixels,
            caveat_codes=("no_comparison_available",),
        )

    if sample_pixels < MIN_NEIGHBOURHOOD_PIXELS:
        return Productivity(
            plot_amplitude=round(plot_amplitude, 3),
            percentiles=usable,
            percentile=None,
            band="unknown",
            neighbourhood_km=neighbourhood_km,
            sample_pixels=sample_pixels,
            caveat_codes=("neighbourhood_too_small",),
        )

    if season_coverage < 0.6:
        # A season half-hidden by cloud understates the peak, which understates
        # the amplitude, which drags the plot down the ranking for a reason
        # that has nothing to do with the field.
        caveats.append("cloud_may_understate")

    percentile = _percentile_of(plot_amplitude, usable)

    # Always said, never inferred: this is biomass, not grain, and the
    # neighbours may not be growing the same thing.
    caveats.append("not_a_yield_measure")

    return Productivity(
        plot_amplitude=round(plot_amplitude, 3),
        percentiles={int(k): round(v, 3) for k, v in usable.items()},
        percentile=percentile,
        band=_band_for(percentile),
        neighbourhood_km=neighbourhood_km,
        sample_pixels=sample_pixels,
        caveat_codes=tuple(caveats),
    )


def amplitude_of(values: Sequence[float | None]) -> float | None:
    """Peak minus trough across a series, ignoring gaps.

    Used only where a series is already to hand. The figure compared against
    the neighbourhood is computed in Earth Engine from the same imagery and
    compositing as the neighbourhood itself — monthly means smooth peaks, so
    mixing the two would make every plot look less vigorous than its
    surroundings for purely arithmetic reasons.
    """
    observed = [v for v in values if v is not None]
    if len(observed) < 2:
        return None
    return round(max(observed) - min(observed), 3)
