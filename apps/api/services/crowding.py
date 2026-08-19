"""District crowding: is everyone about to grow the same thing?

THE FEATURE AS ORIGINALLY SPECIFIED CANNOT BE BUILT HONESTLY
------------------------------------------------------------
"Glut risk" means too many farmers plant one crop and the price collapses at
harvest. Computing that needs to know what farmers across a district intend to
sow. We do not know that, and no public dataset publishes sowing intentions at
district level in time to act on them.

The tempting move is a plausible-looking aggregate — "62% of Nashik plots are
going to onion this season". It would demo beautifully and it would be an
invention. Every other number in this project is traceable to a source, and one
fabricated statistic contaminates the credibility of all of them.

So this module answers two narrower questions that ARE answerable, and refuses
the one that is not.

SIGNAL 1: CONCENTRATION IN OUR OWN ADVICE
-----------------------------------------
We store every advisory we issue, with its district. So we can say truthfully:
"this tool ranked wheat first in 9 of the 14 advisories it has issued for
Ludhiana this rabi season."

That is a statement about THIS TOOL, not about farmers, and the distinction is
the whole point. It is worth showing for a reason that is not obvious: if this
app recommends the same crop to everyone in a district, the app is itself a
glut risk. An advisory that is taken seriously at scale changes the thing it is
predicting. Saying so out loud is the honest disclosure, and it is also the
most interesting thing on the panel.

Every phrase this module emits counts ADVISORIES. Nothing here may be worded as
a count of farmers, plots, hectares or intentions — see test_crowding.py, which
fails on those words appearing in the rendered strings.

SIGNAL 2: WHAT THE MARKET ALREADY DID
-------------------------------------
A glut leaves a fingerprint in prices: the crop gets cheap in the month it is
harvested, because that is when everyone is selling. That IS observable, from
the Agmarknet prices we record. It is backward-looking — it describes previous
harvests, not this one — and the wording says so.

BOTH SIGNALS REFUSE TO CONCLUDE ON THIN DATA
--------------------------------------------
Below the minimums, the band is "unknown" and no percentage is produced at all.
A share computed from four advisories is not a weak finding, it is noise with a
percent sign on it, and once rendered nobody can tell the difference.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Literal

# Reused, not redefined: the price outlook panel already decides when price
# history is deep enough to speak. Two panels on one screen disagreeing about
# whether there is enough data is precisely the contradiction this codebase
# keeps having to fix.
from apps.api.services.price_outlook import MIN_OBSERVATIONS_FOR_SEASONAL

# --------------------------------------------------------------- thresholds

#: Share bands for concentration. Width 0.25.
CROWDED_SHARE = 0.50
COMMON_SHARE = 0.25

#: Minimum advisories before a share is reported at all.
#:
#: Derived, not chosen: one extra advisory moves the share by 1/N. For the
#: number to mean anything, that step has to be smaller than half a band width
#: (0.125), so N must be at least 8. Below that, a single farmer opening the
#: app twice would move the district from "uncommon" to "common".
MIN_ADVISORIES = 8

#: How far below the rest of the year the harvest month has to sit.
#:
#: These are display bands over a ratio that is always shown as a number
#: beside them, so the band never replaces the figure. The 5% floor is there
#: because mandi modal prices move by a few per cent week to week for reasons
#: that have nothing to do with volume; calling anything smaller a "dip" would
#: be reading noise. The 15% line is a judgement call and has NOT been reviewed
#: by an agricultural economist — it sits with the crops.yaml thresholds on the
#: list of things that need an expert before this is relied on.
STEEP_DIP = 0.15
MILD_DIP = 0.05

# Codes are BARE — "advice_crowded", not "crowding.advice_crowded".
#
# The client resolves them as `server.<group>.<code>` with group "crowding", so
# a code carrying its own group produced `server.crowding.crowding.advice_
# crowded`, matched nothing, and fell back to the empty string the panel passes
# as its fallback. The result was a page of correct badges above blank
# sentences and two empty amber boxes — no error anywhere, just missing prose.

ConcentrationBand = Literal["crowded", "common", "uncommon", "never", "unknown"]
DipBand = Literal["steep", "mild", "none", "unknown"]
PriceScope = Literal["district", "national", "none"]


@dataclass(frozen=True)
class AdviceConcentration:
    """How often this tool put this crop first, in this district and season."""

    crop_code: str
    times_ranked_first: int
    advisories_total: int
    share: float | None
    band: ConcentrationBand
    code: str
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class HarvestDip:
    """What this crop fetched at harvest time, against the rest of the year."""

    crop_code: str
    harvest_month: int | None
    harvest_median: int | None
    other_median: int | None
    dip_fraction: float | None
    band: DipBand
    observations: int
    scope: PriceScope
    code: str
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Crowding:
    crop_code: str
    concentration: AdviceConcentration
    dip: HarvestDip
    caveat_codes: list[str] = field(default_factory=list)
    seeded_advisories: int = 0
    """How many of `advisories_total` came from the seeding script."""


# ------------------------------------------------------------ concentration


def concentration(
    crop_code: str,
    *,
    times_ranked_first: int,
    advisories_total: int,
) -> AdviceConcentration:
    """Where this crop sits in our own advice for the district.

    `advisories_total` is every advisory issued for the district and season,
    not just those featuring this crop — otherwise the share would be 100% for
    whichever crop happened to be looked at.
    """
    if advisories_total < MIN_ADVISORIES:
        return AdviceConcentration(
            crop_code=crop_code,
            times_ranked_first=times_ranked_first,
            advisories_total=advisories_total,
            share=None,
            band="unknown",
            # Names the count, so the reader can see how thin it is rather
            # than being told only that we will not say.
            code="too_few_advisories",
            params={"advisories": advisories_total, "needed": MIN_ADVISORIES},
        )

    share = times_ranked_first / advisories_total

    if times_ranked_first == 0:
        # Zero is its own band, not the bottom of "uncommon".
        #
        # Folding it in produced "Ranked first in only 0 of the 12 advisories"
        # under a badge reading "Rarely suggested" — two statements about the
        # same crop that do not agree, since "rarely" means sometimes and this
        # crop was never once put first. The distinction is also real: a crop
        # that led no advisory is telling the farmer something different from
        # one that led two.
        band: ConcentrationBand = "never"
    elif share >= CROWDED_SHARE:
        band = "crowded"
    elif share >= COMMON_SHARE:
        band = "common"
    else:
        band = "uncommon"

    return AdviceConcentration(
        crop_code=crop_code,
        times_ranked_first=times_ranked_first,
        advisories_total=advisories_total,
        share=round(share, 3),
        band=band,
        code=f"advice_{band}",
        params={
            "first": times_ranked_first,
            "advisories": advisories_total,
            "percent": round(share * 100),
            "crop_code": crop_code,
        },
    )


# ------------------------------------------------------------- harvest dip


def harvest_dip(
    crop_code: str,
    *,
    harvest_month: int | None,
    harvest_month_prices: list[int],
    other_month_prices: list[int],
    scope: PriceScope = "district",
) -> HarvestDip:
    """Compare harvest-month prices against the rest of the year.

    Medians, not means: a single freak entry in a thin sample would otherwise
    decide the band.
    """
    observations = len(harvest_month_prices) + len(other_month_prices)

    def unknown(code: str, params: dict) -> HarvestDip:
        return HarvestDip(
            crop_code=crop_code,
            harvest_month=harvest_month,
            harvest_median=None,
            other_median=None,
            dip_fraction=None,
            band="unknown",
            observations=observations,
            scope="none",
            code=code,
            params=params,
        )

    if harvest_month is None:
        return unknown("no_harvest_month", {})

    if (
        len(harvest_month_prices) < MIN_OBSERVATIONS_FOR_SEASONAL
        or len(other_month_prices) < MIN_OBSERVATIONS_FOR_SEASONAL
    ):
        # Both sides matter. Plenty of harvest-month prices against three
        # readings from the rest of the year would produce a confident
        # comparison with nothing to compare to.
        #
        # But WHICH side is missing is the useful part, and the two cases are
        # not alike. A store with 360 prices from other months and none from
        # April is waiting for April; a store with four of each is simply new.
        # Reporting both as "not enough price history" told a farmer we had
        # nothing when we had most of what we needed.
        counts = {
            "harvest_seen": len(harvest_month_prices),
            "other_seen": len(other_month_prices),
            "needed": MIN_OBSERVATIONS_FOR_SEASONAL,
        }
        if len(other_month_prices) >= MIN_OBSERVATIONS_FOR_SEASONAL:
            return unknown("harvest_month_not_seen_yet", counts)
        return unknown("too_little_price_history", counts)

    harvest_median = int(statistics.median(harvest_month_prices))
    other_median = int(statistics.median(other_month_prices))

    if other_median <= 0:
        return unknown("too_little_price_history", {"harvest_seen": 0, "other_seen": 0,
                                                            "needed": MIN_OBSERVATIONS_FOR_SEASONAL})

    dip = (other_median - harvest_median) / other_median

    if dip >= STEEP_DIP:
        band: DipBand = "steep"
    elif dip >= MILD_DIP:
        band = "mild"
    else:
        band = "none"

    return HarvestDip(
        crop_code=crop_code,
        harvest_month=harvest_month,
        harvest_median=harvest_median,
        other_median=other_median,
        dip_fraction=round(dip, 3),
        band=band,
        observations=observations,
        scope=scope,
        code=f"dip_{band}",
        params={
            "percent": round(abs(dip) * 100),
            "harvest_price": harvest_median,
            "other_price": other_median,
            "observations": observations,
            "crop_code": crop_code,
        },
    )


# ------------------------------------------------------------------ combine


def build(
    crop_code: str,
    *,
    times_ranked_first: int,
    advisories_total: int,
    harvest_month: int | None,
    harvest_month_prices: list[int],
    other_month_prices: list[int],
    price_scope: PriceScope = "district",
    seeded_advisories: int = 0,
) -> Crowding:
    conc = concentration(
        crop_code,
        times_ranked_first=times_ranked_first,
        advisories_total=advisories_total,
    )
    dip = harvest_dip(
        crop_code,
        harvest_month=harvest_month,
        harvest_month_prices=harvest_month_prices,
        other_month_prices=other_month_prices,
        scope=price_scope,
    )

    caveats: list[str] = [
        # Never omitted. The single most likely misreading of this panel is
        # that the share describes farmers rather than advisories, and the
        # panel is worthless — worse than absent — if it is read that way.
        "advisories_not_farmers",
    ]

    if dip.band != "unknown":
        # The dip is history. It says what happened at previous harvests, and
        # a farmer reading it as a forecast for this one has over-read it.
        caveats.append("dip_is_backward_looking")

    if dip.scope == "national":
        caveats.append("prices_not_local")

    if dip.band == "unknown" and dip.code in {
        "harvest_month_not_seen_yet",
        "too_little_price_history",
    }:
        # Said once for the panel, not repeated under every crop.
        #
        # The reason this column is empty is not obvious and is not the user's
        # fault: data.gov.in publishes only a CURRENT daily snapshot, with no
        # historical endpoint, so a seasonal picture can only be accumulated by
        # observing prices over time. Without saying so, an empty column reads
        # as a broken feature rather than one that has not had a year yet.
        caveats.append("price_history_accrues")

    if seeded_advisories > 0:
        # A fresh install has nothing to count, so the seeding script generates
        # advisories across the demo districts to give this panel something to
        # show. They are genuine output of the same recommender — but they were
        # not asked for by anyone, and a total that quietly mixed them with
        # real use would overstate how much this tool is being consulted. Which
        # is the same class of overstatement the whole feature was rebuilt to
        # avoid, so it gets said rather than assumed.
        caveats.append("includes_seeded")

    return Crowding(
        crop_code=crop_code,
        concentration=conc,
        dip=dip,
        caveat_codes=caveats,
        seeded_advisories=seeded_advisories,
    )
