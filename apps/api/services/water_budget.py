"""How much water a crop needs here, how much the rain will give, and the gap.

THE MOST IMPORTANT THING ON THIS PAGE IS A CAVEAT
-------------------------------------------------
The rainfall figure is a **thirty-year normal**, not a forecast. CHIRPS gives us
what this district usually receives between 1994 and 2023; it says nothing about
what will fall this year, and monsoon rainfall in India routinely lands 30-40%
either side of its own average.

So a budget that balances on paper can still fail in the field. Everything this
module returns is framed as planning guidance, and the API text says so rather
than leaving a farmer to infer it from a number that looks precise.

HOW THE GAP IS WORKED OUT
-------------------------
    effective rainfall   what the crop can actually use, after runoff and
                         percolation — always less than what falls
    requirement          the crop's seasonal need from crops.yaml
    deficit              requirement - effective rainfall, floored at zero
    waterings            deficit / a typical application depth

Effective rainfall uses the USDA Soil Conservation Service method, which is
defined per MONTH. Applying it to a whole season's total in one go understates
it badly — 850 mm in one lump returns 210 mm, while the same rain spread over
four months returns about 580 mm. So the season is divided into months first.
That assumes rain falls evenly through the season, which it does not; the note
in the response says so.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from services.ml.types import CropSpec

Status = Literal["rain_sufficient", "needs_irrigation", "cannot_meet", "surplus", "unknown"]

#: mm delivered per watering. Indian extension guidance is typically 5-7 cm;
#: this is the middle of that. Soil texture would refine it, which is a reason
#: the count is presented as "about N" rather than a precise number.
APPLICATION_DEPTH_MM = 60.0

#: 1 mm of water over 1 hectare is 10 cubic metres. Not an assumption — a unit
#: conversion, and the only exact arithmetic in this file.
M3_PER_MM_PER_HA = 10.0

#: Rain beyond this multiple of the crop's upper need is a drainage problem
#: rather than a bonus. Rice excepted, which is grown standing in water.
SURPLUS_RATIO = 1.3

DAYS_PER_MONTH = 30.0


def effective_rainfall_mm(total_mm: float, duration_days: int) -> float:
    """USDA SCS effective rainfall, applied month by month.

    The formula is defined for monthly totals. Feeding it a seasonal sum
    directly is a real and easy mistake: it treats the whole monsoon as one
    downpour and writes most of it off as runoff.
    """
    if total_mm <= 0:
        return 0.0

    months = max(duration_days / DAYS_PER_MONTH, 1.0)
    monthly = total_mm / months

    if monthly <= 250.0:
        effective_monthly = monthly * (125.0 - 0.2 * monthly) / 125.0
    else:
        effective_monthly = 125.0 + 0.1 * monthly

    # Cannot be more use than actually fell.
    return round(min(effective_monthly * months, total_mm), 1)


@dataclass(frozen=True)
class WaterBudget:
    crop_code: str
    name: str

    requirement_mm: int
    """Lower end of the crop's seasonal need. Below this, yield suffers."""

    comfortable_mm: int
    """Upper end. Between the two the crop is well watered."""

    season_rainfall_mm: float | None
    effective_rainfall_mm: float | None

    deficit_mm: float | None
    """What irrigation has to supply. Zero when rain covers it."""

    deficit_m3: float | None
    """The same gap as a volume for this plot, which is what a pump moves."""

    waterings: int | None
    """Waterings to reach the MINIMUM of the crop's band, not the middle.

    Stated because the panel shows a range. "Needs 400-650 mm, gap 325 mm"
    invites the reader to think the gap lands them comfortably inside it; it
    lands them on 400, the bottom edge. The comfortable figures below let the
    UI say so instead of leaving a farmer to work it out.
    """

    waterings_comfortable: int | None
    deficit_comfortable_mm: float | None

    surplus_mm: float | None
    status: Status
    can_be_met: bool
    """False when the gap exists and there is no irrigation to close it."""


def build(
    crop: CropSpec,
    *,
    season_rainfall_mm: float | None,
    area_ha: float,
    irrigation: str,
) -> WaterBudget:
    low, high = crop.rainfall_mm
    requirement = int(round(low))
    comfortable = int(round(high))

    if season_rainfall_mm is None:
        # No rainfall reading. Returning a deficit of zero here would read as
        # "no irrigation needed", which is the opposite of what we know.
        return WaterBudget(
            crop_code=crop.crop_code,
            name=crop.name,
            requirement_mm=requirement,
            comfortable_mm=comfortable,
            season_rainfall_mm=None,
            effective_rainfall_mm=None,
            deficit_mm=None,
            deficit_m3=None,
            waterings=None,
            waterings_comfortable=None,
            deficit_comfortable_mm=None,
            surplus_mm=None,
            status="unknown",
            can_be_met=True,
        )

    effective = effective_rainfall_mm(season_rainfall_mm, crop.duration_days)
    deficit = max(round(low - effective, 1), 0.0)
    surplus = max(round(effective - high * SURPLUS_RATIO, 1), 0.0)

    has_irrigation = irrigation != "rainfed"

    if deficit > 0:
        status: Status = "needs_irrigation" if has_irrigation else "cannot_meet"
    elif surplus > 0:
        status = "surplus"
    else:
        status = "rain_sufficient"

    deficit_comfortable = max(round(high - effective, 1), 0.0)

    return WaterBudget(
        crop_code=crop.crop_code,
        name=crop.name,
        requirement_mm=requirement,
        comfortable_mm=comfortable,
        season_rainfall_mm=round(season_rainfall_mm, 1),
        effective_rainfall_mm=effective,
        deficit_mm=deficit,
        deficit_m3=round(deficit * M3_PER_MM_PER_HA * area_ha) if deficit > 0 else 0,
        waterings=math.ceil(deficit / APPLICATION_DEPTH_MM) if deficit > 0 else 0,
        deficit_comfortable_mm=deficit_comfortable,
        waterings_comfortable=(
            math.ceil(deficit_comfortable / APPLICATION_DEPTH_MM)
            if deficit_comfortable > 0
            else 0
        ),
        surplus_mm=surplus,
        status=status,
        can_be_met=has_irrigation or deficit == 0,
    )
