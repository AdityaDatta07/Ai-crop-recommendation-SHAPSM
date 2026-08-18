"""Sentinel-2 spectral indices.

Which indices, and why these four:

  NDVI  (B8-B4)/(B8+B4)                Vegetation vigour. The standard, but it
                                       saturates over dense canopy and is
                                       distorted by bare soil - which is exactly
                                       what a field looks like before sowing.

  SAVI  (B8-B4)/(B8+B4+L) * (1+L)      NDVI corrected for soil brightness,
                                       L=0.5. Earns its place precisely because
                                       fields awaiting sowing are sparse or bare,
                                       where NDVI is least trustworthy.

  NDMI  (B8-B11)/(B8+B11)              Canopy water content. The one that speaks
                                       to irrigation planning rather than to how
                                       green things look.

  EVI   2.5*(B8-B4)/(B8+6*B4-7.5*B2+1) Like NDVI but resists saturation and
                                       corrects for atmosphere and soil
                                       background. Useful on dense standing crop.

Deliberately NOT included: NDWI. McFeeters' formulation (B3-B8) detects open
water, which on a farm plot mostly means flooding, and Gao's formulation is
NDMI under another name. Showing both would present the same measurement twice
and imply more information than exists.

The honest caveat, which the API passes through to the screen: all of these
describe what is growing on the plot NOW. For a pre-sowing decision that is
weak evidence. The `history` series is the part that actually informs a
recommendation - it shows what the field has supported across past seasons.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import date, timedelta

from services.geo.types import ResolvedLocation

# Sentinel-2 revisit is 5 days with both satellites; cloud cover makes the
# usable cadence longer. Anything older than this is stale enough to say so.
MAX_USEFUL_AGE_DAYS = 30

# Distinguishes "caller did not supply NDVI" from "NDVI is known to be
# unavailable". Both look like None otherwise, and conflating them is how the
# panel ended up inventing 0.556 for a field whose imagery was clouded out.
_UNSET = object()


@dataclass(frozen=True)
class IndexValue:
    key: str
    name: str
    value: float | None
    """None means cloud cover or no acquisition - never substitute a number."""
    range_min: float
    range_max: float
    interpretation: str
    formula: str


@dataclass(frozen=True)
class HistoryPoint:
    date: date
    ndvi: float | None


@dataclass(frozen=True)
class IndicesResult:
    observed_on: date | None
    cloud_cover_pct: float | None
    indices: tuple[IndexValue, ...]
    history: tuple[HistoryPoint, ...]
    source: str
    tile_url_template: str | None
    """Sentinel-2 overlay tiles. None when Earth Engine is not configured."""


DEFINITIONS = {
    "ndvi": {
        "name": "Vegetation vigour (NDVI)",
        "range": (-1.0, 1.0),
        "formula": "(B8 - B4) / (B8 + B4)",
    },
    "savi": {
        "name": "Soil-adjusted vigour (SAVI)",
        "range": (-1.0, 1.0),
        "formula": "((B8 - B4) / (B8 + B4 + 0.5)) * 1.5",
    },
    "ndmi": {
        "name": "Canopy moisture (NDMI)",
        "range": (-1.0, 1.0),
        "formula": "(B8 - B11) / (B8 + B11)",
    },
    "evi": {
        "name": "Enhanced vegetation (EVI)",
        "range": (-1.0, 1.0),
        "formula": "2.5 * (B8 - B4) / (B8 + 6*B4 - 7.5*B2 + 1)",
    },
}


def interpret(key: str, value: float | None) -> str:
    """Plain-language reading. A number a farmer cannot act on is decoration."""
    if value is None:
        return "No clear satellite image available for this period."

    if key in ("ndvi", "savi"):
        if value < 0.15:
            return "Bare soil or stubble — the plot reads as fallow and ready."
        if value < 0.35:
            return "Sparse cover — early growth, weeds, or crop residue."
        if value < 0.6:
            return "Moderate growth — an established crop mid-season."
        return "Dense canopy — a vigorous standing crop."

    if key == "ndmi":
        if value < -0.1:
            return "Very dry — bare or severely water-stressed."
        if value < 0.1:
            return "Low moisture — irrigation would likely be needed early."
        if value < 0.3:
            return "Adequate moisture for most crops."
        return "High moisture — well watered, or recently irrigated."

    if key == "evi":
        if value < 0.2:
            return "Little live biomass."
        if value < 0.4:
            return "Moderate biomass."
        return "High biomass — dense, healthy canopy."

    return ""


def _seed(place: ResolvedLocation) -> int:
    return int(hashlib.sha256(place.district_code.encode()).hexdigest()[:8], 16)


def _mock_value(seed: int, offset: int, low: float, high: float) -> float:
    bucket = (seed >> (offset * 4)) % 1000
    return round(low + (high - low) * (bucket / 1000.0), 3)


def mock_indices(
    place: ResolvedLocation,
    today: date,
    ndvi_current: float | None | object = _UNSET,
) -> IndicesResult:
    """Deterministic, plausible, and labelled as synthetic.

    Same rule as the rest of the mock layer: it may be made up, but it must
    never claim to be measured.
    """
    seed = _seed(place)

    # NDVI must match conditions.ndvi_current exactly. They are the same
    # measurement of the same field, and showing 0.18 in one panel and 0.39 in
    # another on the same screen destroys trust in every other number on it.
    #
    # An explicit None means the imagery was clouded out. That propagates: every
    # index derived from the same bands is unavailable too, and the panel shows
    # dashes rather than a plausible-looking invention.
    ndvi: float | None
    if ndvi_current is _UNSET:
        ndvi = _mock_value(seed, 1, 0.12, 0.68)
    else:
        ndvi = ndvi_current  # type: ignore[assignment]
    # SAVI tracks NDVI but is lower on sparse cover, which is the whole point
    # of the index. Keeping that relationship makes the mock internally honest.
    # SAVI and EVI share the red and NIR bands with NDVI, so if NDVI could not
    # be measured neither can they. NDMI uses SWIR and is treated the same way -
    # one cloudy acquisition blocks the lot.
    savi = round(ndvi * 0.85, 3) if ndvi is not None else None
    evi = round(ndvi * 0.78, 3) if ndvi is not None else None
    ndmi = _mock_value(seed, 2, -0.15, 0.42) if ndvi is not None else None

    values: dict[str, float | None] = {"ndvi": ndvi, "savi": savi, "ndmi": ndmi, "evi": evi}

    indices = tuple(
        IndexValue(
            key=key,
            name=str(spec["name"]),
            value=values[key],
            range_min=float(spec["range"][0]),
            range_max=float(spec["range"][1]),
            interpretation=interpret(key, values[key]),
            formula=str(spec["formula"]),
        )
        for key, spec in DEFINITIONS.items()
    )

    # Two years of monthly NDVI with a seasonal shape, so the history chart
    # shows the double-cropping pattern a real Indian plot would.
    history: list[HistoryPoint] = []
    for months_ago in range(23, -1, -1):
        point_date = today - timedelta(days=months_ago * 30)
        month = point_date.month
        # Peaks around Sep (kharif) and Feb (rabi), troughs between.
        seasonal = 0.5 + 0.28 * math.sin((month - 4) * math.pi / 6)
        jitter = ((seed >> (months_ago % 8)) % 100) / 1000.0
        history.append(HistoryPoint(date=point_date, ndvi=round(min(0.92, seasonal + jitter), 3)))

    return IndicesResult(
        # No usable acquisition means no observation date to report.
        observed_on=(today - timedelta(days=(seed % 9))) if ndvi is not None else None,
        cloud_cover_pct=round(_mock_value(seed, 3, 0.0, 28.0), 1) if ndvi is not None else None,
        indices=indices,
        history=tuple(history) if ndvi is not None else (),
        source="Synthetic mock data (USE_MOCK_GEO=true) — not measured",
        tile_url_template=None,
    )
