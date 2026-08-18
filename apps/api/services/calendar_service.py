"""Turns the reference sowing window into real dates for this season.

crops.yaml stores month-day only, because a crop calendar is not year-specific.
The year is resolved at request time against today's date.
"""

from __future__ import annotations

from datetime import date, timedelta

from services.ml.types import CropSpec


def _window_for_year(month_day: str, year: int) -> date:
    month, day = (int(part) for part in month_day.split("-"))
    return date(year, month, day)


def resolve_calendar(
    crop: CropSpec,
    today: date,
    sowing_date: date | None = None,
) -> tuple[date, date, date, date]:
    """Return (sowing_start, sowing_end, harvest_start, harvest_end).

    If the farmer gave a sowing date we anchor the harvest to it but still show
    the recommended window, so they can see whether their plan sits inside it.
    """
    start_md = crop.sowing_window.start
    end_md = crop.sowing_window.end

    # Use this year's window if it has not closed yet, otherwise next year's.
    # No crop in the reference set has a window that straddles new year, which
    # keeps this simple - revisit if one is added.
    year = today.year
    if _window_for_year(end_md, year) < today:
        year += 1

    sowing_start = _window_for_year(start_md, year)
    sowing_end = _window_for_year(end_md, year)

    anchor = sowing_date or sowing_start
    harvest_start = anchor + timedelta(days=crop.duration_days)
    harvest_end = (sowing_date or sowing_end) + timedelta(days=crop.duration_days)

    return sowing_start, sowing_end, harvest_start, harvest_end
