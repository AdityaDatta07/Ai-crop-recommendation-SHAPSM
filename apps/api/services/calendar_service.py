"""Turns the reference sowing window into real dates for this season.

crops.yaml stores month-day only, because a crop calendar is not year-specific.
The year is resolved at request time against today's date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from services.ml.types import CropSpec


def _window_for_year(month_day: str, year: int) -> date:
    month, day = (int(part) for part in month_day.split("-"))
    return date(year, month, day)


@dataclass(frozen=True)
class ResolvedCalendar:
    sowing_start: date
    sowing_end: date
    harvest_start: date
    harvest_end: date

    days_until_sowing: int
    """Negative while the window is open, positive before it opens."""

    window_status: str
    """open | upcoming | closed_this_year

    "closed_this_year" is the one that needs saying out loud: asked in August
    about kharif, the honest answer is that sowing closed in July and these
    dates are for next year. Without this the app silently shows a June 2027
    sowing date and leaves the farmer to notice the year.
    """


def resolve_calendar(
    crop: CropSpec,
    today: date,
    sowing_date: date | None = None,
) -> tuple[date, date, date, date]:
    """Return (sowing_start, sowing_end, harvest_start, harvest_end).

    Kept for callers that only want the dates; resolve_calendar_full carries
    the window status too.
    """
    resolved = resolve_calendar_full(crop, today, sowing_date)
    return (
        resolved.sowing_start,
        resolved.sowing_end,
        resolved.harvest_start,
        resolved.harvest_end,
    )


def resolve_calendar_full(
    crop: CropSpec,
    today: date,
    sowing_date: date | None = None,
) -> ResolvedCalendar:
    """Dates plus whether this season's window is still open.

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

    # Did we have to roll forward a year to find an open window?
    this_year_end = _window_for_year(end_md, today.year)
    rolled_forward = this_year_end < today

    if sowing_start <= today <= sowing_end:
        status = "open"
    elif rolled_forward:
        status = "closed_this_year"
    else:
        status = "upcoming"

    return ResolvedCalendar(
        sowing_start=sowing_start,
        sowing_end=sowing_end,
        harvest_start=harvest_start,
        harvest_end=harvest_end,
        days_until_sowing=(sowing_start - today).days,
        window_status=status,
    )
