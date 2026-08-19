"""What the field has actually been doing, read off two years of NDVI.

WHAT THIS ANSWERS, AND WHAT IT DELIBERATELY DOES NOT
-----------------------------------------------------
The original plan was to identify the crop from satellite imagery. That was
altered, and rightly: distinguishing wheat from barley from mustard by spectral
signature needs labelled ground-truth for these districts, which we do not have,
and a confident wrong answer about somebody's own field destroys trust in
everything else on the page.

What a vegetation index CAN support is coarser and still worth knowing:

    intensity   how many crop cycles a year this plot runs
    timing      which seasons those cycles fall in
    fallow      how long the ground sits bare

A farmer already knows this about their own field. The value is in the plot
they have just bought, rented or inherited, in checking a claim before renting,
and in the app noticing when its assumptions and the ground disagree.

HOW A CYCLE IS DETECTED
-----------------------
A crop is a rise and a fall. NDVI climbs from bare soil as the canopy closes,
peaks near flowering, and drops at senescence and harvest. So a cycle is a
PEAK with a real descent on both sides.

The obvious implementation — count runs above a greenness threshold — was
tried and is wrong twice over:

  * Where paddy is followed straight by wheat, NDVI never returns to bare soil
    between them. An eight-month run above the threshold counted as one crop
    when it was two.

  * A series that opens mid-season starts with the tail of a crop sown before
    the record begins. Counted whole, it turns a rabi-only plot into a
    double-cropped one.

So peaks are located directly and split where the canopy dips between them.

INTENSITY COMES FROM SEASONS, NOT FROM A CYCLE COUNT
-----------------------------------------------------
Dividing complete cycles by elapsed years is fragile. A peak at either end of
the record has no observed rise or fall, so two years of an annually cropped
field yield one countable cycle and a rate of 0.5 — an annual crop reported as
half-annual.

What survives that is WHICH SEASONS carry a peak. A field with rabi peaks and
nothing in kharif is single-cropped; one with both is double-cropped; all three
is triple. Partial peaks still count towards this, because a truncated peak is
still evidence a crop was there — it is only its extent we could not measure.

THE BIAS THIS CARRIES, WHICH MUST BE STATED
-------------------------------------------
Sentinel-2 is optical, and the Indian kharif season is the cloudiest part of
the year. Months with no clear acquisition come back null. A missed monsoon
peak makes a double-cropped field look single-cropped — the error runs in ONE
direction, always understating intensity, never overstating it.

So coverage is measured per season and reported, and a gap in the kharif
window downgrades confidence rather than being silently averaged over.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

Intensity = Literal["single", "double", "triple", "fallow", "uncropped", "unknown"]
Confidence = Literal["high", "medium", "low"]

# --------------------------------------------------------------------- tuning

#: Below this the ground reads as bare or stubble rather than a growing crop.
#: NDVI over dry soil in India typically sits at 0.1-0.2.
BARE_SOIL_NDVI = 0.25

#: Above this a canopy is genuinely closed over the plot.
GROWING_NDVI = 0.40

#: A rise smaller than this is noise, haze, or a weed flush after rain — not a
#: crop somebody planted and harvested.
MIN_AMPLITUDE = 0.15

#: A crop occupies the ground for months. One green month between two bare ones
#: is far more likely to be a bad cloud mask than a harvest.
MIN_CYCLE_MONTHS = 2

#: How far NDVI must fall between two peaks for them to be separate crops.
#: Paddy followed by wheat dips as the first is harvested and the second
#: emerges, but rarely all the way to bare soil — so this is smaller than the
#: bare-soil threshold and larger than sensor noise.
MIN_DIP_BETWEEN_PEAKS = 0.12

#: Which months belong to which season. Same windows the geo service uses, so
#: a cycle dated here and a rainfall figure computed there refer to the same
#: part of the year.
SEASON_MONTHS = {
    "kharif": (6, 7, 8, 9, 10),
    "rabi": (11, 12, 1, 2, 3),
    "zaid": (4, 5),
}

#: Kharif is the cloudy season. Coverage below this means we may simply not
#: have seen the monsoon crop, and must not conclude it was absent.
MIN_SEASON_COVERAGE = 0.5


@dataclass(frozen=True)
class Cycle:
    """One rise and fall of the canopy: a crop, grown and taken off."""

    peak_month: str
    """YYYY-MM of the greenest observation in this run."""

    peak_ndvi: float
    season: str
    start_month: str
    end_month: str
    months: int


@dataclass(frozen=True)
class CropHistory:
    cycles: tuple[Cycle, ...]
    cycles_per_year: float
    """Complete cycles per observed year. A diagnostic, not the intensity.

    Always an undercount: peaks at either end of the record cannot be
    bracketed, so they are excluded. `intensity` is derived from seasons for
    exactly this reason.
    """

    intensity: Intensity
    seasons_used: tuple[str, ...]

    fallow_months: int
    """Months observed at or below bare soil. Excludes months never seen."""

    observed_months: int
    total_months: int
    season_coverage: dict
    """Fraction of each season's months that had a usable reading."""

    confidence: Confidence
    caveat_codes: tuple[str, ...]
    """Message codes for what limits this reading. Localised client-side."""


# ------------------------------------------------------------------ internals


def _season_of(month: int) -> str:
    for season, months in SEASON_MONTHS.items():
        if month in months:
            return season
    return "rabi"


def _month_key(iso_date: str) -> str:
    return iso_date[:7]


def _month_number(iso_date: str) -> int:
    return int(iso_date[5:7])


def _find_cycles(
    points: Sequence[tuple[str, float | None]],
) -> tuple[list[Cycle], list[str]]:
    """Locate peaks, and report how many were too truncated to count.

    A null breaks the series rather than being interpolated across. Filling a
    cloud gap would invent a canopy nobody observed, and the whole point of
    this module is that a missing month is missing, not zero.
    """
    cycles: list[Cycle] = []
    partial_seasons: list[str] = []

    # Split into stretches of consecutive observed months. A gap means we
    # cannot say what happened, so peaks are never inferred across one.
    segments: list[list[tuple[str, float]]] = []
    current: list[tuple[str, float]] = []
    for iso_date, ndvi in points:
        if ndvi is None:
            if current:
                segments.append(current)
            current = []
        else:
            current.append((iso_date, ndvi))
    if current:
        segments.append(current)

    for segment in segments:
        values = [value for _, value in segment]

        # Candidate peaks: local maxima that clear the growing threshold.
        peaks: list[int] = []
        for i, value in enumerate(values):
            if value < GROWING_NDVI:
                continue
            left = values[i - 1] if i > 0 else None
            right = values[i + 1] if i + 1 < len(values) else None
            if (left is None or value >= left) and (right is None or value >= right):
                peaks.append(i)

        # Collapse peaks that are not separated by a real descent: a plateau
        # across two months is one crop, not two.
        merged: list[int] = []
        for index in peaks:
            if merged:
                between = values[merged[-1] : index + 1]
                if between and max(values[merged[-1]], values[index]) - min(between) < (
                    MIN_DIP_BETWEEN_PEAKS
                ):
                    if values[index] > values[merged[-1]]:
                        merged[-1] = index
                    continue
            merged.append(index)

        for index in merged:
            peak_date, peak_ndvi = segment[index]

            # Walk out to the troughs either side of this peak.
            start = index
            while start > 0 and values[start - 1] <= values[start]:
                start -= 1
            end = index
            while end + 1 < len(values) and values[end + 1] <= values[end]:
                end += 1

            rose = peak_ndvi - values[start]
            fell = peak_ndvi - values[end]

            # A peak needs BOTH sides to be a crop we watched come and go.
            # Missing one means the series began or ended mid-season, or a
            # cloud gap cut it short — real, but not countable.
            if rose < MIN_AMPLITUDE or fell < MIN_AMPLITUDE:
                # The record began or ended mid-season, or a cloud gap cut the
                # peak short. A crop was here; its extent is unmeasurable. It
                # still counts towards which seasons this field uses.
                partial_seasons.append(_season_of(_month_number(peak_date)))
                continue

            if end - start + 1 < MIN_CYCLE_MONTHS:
                continue

            cycles.append(
                Cycle(
                    peak_month=_month_key(peak_date),
                    peak_ndvi=round(peak_ndvi, 3),
                    season=_season_of(_month_number(peak_date)),
                    start_month=_month_key(segment[start][0]),
                    end_month=_month_key(segment[end][0]),
                    months=end - start + 1,
                )
            )

    return cycles, partial_seasons


def _coverage(points: Sequence[tuple[str, float | None]]) -> dict:
    seen: dict[str, list[bool]] = {season: [] for season in SEASON_MONTHS}
    for iso_date, ndvi in points:
        seen[_season_of(_month_number(iso_date))].append(ndvi is not None)

    return {
        season: round(sum(flags) / len(flags), 2) if flags else 0.0
        for season, flags in seen.items()
    }


# ---------------------------------------------------------------------- entry


def analyse(history: Sequence[tuple[str, float | None]]) -> CropHistory:
    """`history` is (ISO date, NDVI or None) in any order, roughly monthly."""
    points = sorted(history, key=lambda item: item[0])

    total = len(points)
    observed = sum(1 for _, ndvi in points if ndvi is not None)

    if observed < 6:
        # Too little to say anything. Saying "single-cropped" from four cloudy
        # months would be a guess wearing a finding's clothes.
        return CropHistory(
            cycles=(),
            cycles_per_year=0.0,
            intensity="unknown",
            seasons_used=(),
            fallow_months=0,
            observed_months=observed,
            total_months=total,
            season_coverage=_coverage(points),
            confidence="low",
            caveat_codes=("too_few_observations",),
        )

    cycles, partial_seasons = _find_cycles(points)
    coverage = _coverage(points)

    years = max(total / 12.0, 0.5)
    per_year = round(len(cycles) / years, 2)

    # Seasons carrying a crop, complete peaks and truncated ones alike.
    seasons = tuple(
        season
        for season in ("kharif", "rabi", "zaid")
        if season in {cycle.season for cycle in cycles} or season in partial_seasons
    )

    fallow = sum(1 for _, ndvi in points if ndvi is not None and ndvi <= BARE_SOIL_NDVI)

    caveats: list[str] = []

    # Cloud in the monsoon is the failure that matters, because it hides crops
    # rather than inventing them.
    if coverage.get("kharif", 0.0) < MIN_SEASON_COVERAGE:
        caveats.append("kharif_cloud_gap")
    if observed / max(total, 1) < 0.6:
        caveats.append("patchy_coverage")
    if total < 18:
        caveats.append("short_baseline")
    if partial_seasons:
        caveats.append("partial_cycles_seen")

    # Intensity is how many seasons of the year this plot is worked.
    #
    # Three ways to have no seasons, and they are not the same thing:
    #
    #   fallow      we watched it, and it was bare
    #   uncropped   we watched it, and it never greened enough to be a crop —
    #               scrub, grass, or a boundary drawn over something that is
    #               not a field at all
    #   unknown     we could not see enough to say
    #
    # Collapsing the middle case into "unknown" produced the screenshot bug:
    # "too few clear satellite passes" printed directly above "20 of 24 months
    # had a clear satellite view". Coverage was fine; the plot simply never
    # grew a crop, which is worth saying out loud.
    seen_enough = observed / max(total, 1) >= 0.6

    if not seasons:
        if fallow >= observed * 0.6:
            intensity: Intensity = "fallow"
        elif seen_enough:
            intensity = "uncropped"
        else:
            intensity = "unknown"
    elif len(seasons) >= 3:
        intensity = "triple"
    elif len(seasons) == 2:
        intensity = "double"
    else:
        intensity = "single"

    # Confidence follows what we could SEE, not how tidy the answer looks.
    #
    # partial_cycles_seen is excluded on purpose. Every finite record has edges,
    # so a peak at either end is always truncated — including in a perfectly
    # clear two-year series. Letting it downgrade confidence meant no reading
    # could ever be "high", which trains a reader to ignore the label.
    limiting = [code for code in caveats if code != "partial_cycles_seen"]

    if limiting or observed / max(total, 1) < 0.75:
        confidence: Confidence = "low" if len(limiting) > 1 else "medium"
    else:
        confidence = "high"

    # "Not clear" beside a high-confidence badge is a contradiction on its face.
    # If we cannot say what the pattern is, we are not confident about it,
    # however clear the sky happened to be.
    if intensity == "unknown":
        confidence = "low"

    # An intensity claim built on a season we could not see is not a claim.
    if intensity in ("single", "fallow") and "kharif_cloud_gap" in caveats:
        caveats.append("may_understate_intensity")

    return CropHistory(
        cycles=tuple(cycles),
        cycles_per_year=per_year,
        intensity=intensity,
        seasons_used=seasons,
        fallow_months=fallow,
        observed_months=observed,
        total_months=total,
        season_coverage=coverage,
        confidence=confidence,
        caveat_codes=tuple(caveats),
    )
