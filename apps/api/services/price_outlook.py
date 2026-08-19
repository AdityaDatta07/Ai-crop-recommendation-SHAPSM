"""What a crop is likely to fetch when it is actually sold.

The problem this solves: today's mandi price is nearly irrelevant to a farmer
choosing what to sow. Wheat sown in November is sold in April. Showing an August
price against an April harvest invites a decision based on a number that will
have moved.

The problem building it: data.gov.in publishes only a CURRENT daily snapshot.
There is no historical price API. So a genuine seasonal forecast needs history
we do not yet have, and inventing a seasonality curve would be exactly the
fabrication this project refuses elsewhere.

The design that follows from those two facts:

  1. Record every price we observe (price_history). History accrues from the day
     this ships, and the forecast improves on its own as it deepens.
  2. Until there is enough history, say so, and fall back to what IS known:
     the MSP floor, which for notified crops is a genuine guarantee at harvest
     because that is when procurement runs.
  3. Label the basis on every outlook, so the screen never implies more
     certainty than the data supports.

`basis` is the honesty dial, and the UI renders it differently for each value.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

logger = logging.getLogger(__name__)

# Below this many observations in the harvest month, a seasonal estimate is
# noise dressed as insight.
MIN_OBSERVATIONS_FOR_SEASONAL = 8

OutlookBasis = Literal["seasonal_history", "msp_floor", "current_only", "none"]


def _month_term(harvest_month: str | None) -> str:
    """The month as an identifier ("december"), not as English ("December").

    A month name is a word like any other; leaving it in English left "December
    का अनुमान" on a Hindi screen. The client has the twelve names.
    """
    if not harvest_month:
        return ""
    try:
        return _MONTH_KEYS[int(harvest_month.split("-")[1]) - 1]
    except (IndexError, ValueError):
        return ""


_MONTH_KEYS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]


@dataclass(frozen=True)
class PriceOutlook:
    """Projected price for the month this crop will actually be sold."""

    harvest_month: str | None
    """YYYY-MM of the middle of the harvest window."""

    expected_per_quintal: int | None
    low_per_quintal: int | None
    high_per_quintal: int | None

    msp_floor_per_quintal: int | None
    current_per_quintal: int | None

    basis: OutlookBasis
    observations_used: int
    explanation: str
    """English. Rendered from explanation_code client-side when a translation exists."""

    explanation_code: str = ""
    explanation_params: dict = field(default_factory=dict)

    below_msp_by: int | None = None
    """How far today's market price sits under the support price, if it does.

    Worth surfacing rather than burying. A crop trading below MSP tells a farmer
    two things at once: the market is weak, and whether they realise the floor
    depends entirely on whether procurement actually reaches them. For maize and
    most pulses it often does not, whatever the notified price says."""


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def build_outlook(
    *,
    crop_name: str,
    crop_code: str = "",
    harvest_start: date | None,
    msp_floor: int | None,
    current_price: int | None,
    harvest_month_history: list[int],
) -> PriceOutlook:
    """Combine what we know into a defensible outlook.

    `harvest_month_history` is prices previously observed for this crop in the
    same calendar month as harvest, across any year. Empty on a fresh install.
    """
    harvest_month = _month_key(harvest_start) if harvest_start else None
    month_name = harvest_start.strftime("%B") if harvest_start else "harvest"

    # Best case: we have actually seen this crop trade in this month before.
    if len(harvest_month_history) >= MIN_OBSERVATIONS_FOR_SEASONAL:
        ordered = sorted(harvest_month_history)
        median = int(statistics.median(ordered))
        # Quartiles rather than min/max: two freak entries should not define the
        # range a farmer plans against.
        low = int(ordered[len(ordered) // 4])
        high = int(ordered[(len(ordered) * 3) // 4])

        return PriceOutlook(
            harvest_month=harvest_month,
            expected_per_quintal=median,
            low_per_quintal=low,
            high_per_quintal=high,
            msp_floor_per_quintal=msp_floor,
            current_per_quintal=current_price,
            basis="seasonal_history",
            observations_used=len(harvest_month_history),
            explanation=(
                f"Based on {len(harvest_month_history)} recorded {month_name} prices for "
                f"{crop_name}. The middle figure is the median; the range covers the "
                "middle half of what was seen."
            ),
            explanation_code="seasonal_history",
            explanation_params={
                "count": len(harvest_month_history),
                "month": _month_term(harvest_month),
                "crop": crop_name,
                "crop_code": crop_code,
            },
        )

    # No usable history. For a notified crop the MSP floor is the firmest thing
    # we know about harvest-time price, which beats a guess.
    if msp_floor is not None:
        gap = (
            msp_floor - current_price
            if current_price is not None and current_price < msp_floor
            else None
        )

        explanation_params = {"month": _month_term(harvest_month), "msp": msp_floor}
        if gap is not None:
            # The market is under the floor. Say so plainly — the economics on
            # this page are computed at the market price, not the floor, and the
            # farmer deserves to know why the two numbers differ.
            explanation_code = "msp_floor_below_market"
            explanation_params |= {
                "crop": crop_name.lower(),
                "crop_code": crop_code,
                "price": current_price,
                "gap": gap,
            }
            explanation = (
                f"Not enough price history yet to project {month_name}. Note that "
                f"{crop_name.lower()} is currently trading at Rs {current_price}/quintal, "
                f"Rs {gap} BELOW its support price of Rs {msp_floor}. The earnings below "
                "use the market price, because procurement does not reach every farmer."
            )
        else:
            explanation_code = "msp_floor"
            explanation = (
                f"Not enough price history yet to project {month_name}. What is certain: "
                f"the support price is Rs {msp_floor}/quintal, and procurement runs at "
                "harvest. Treat that as the floor, not the expected price."
            )

        return PriceOutlook(
            harvest_month=harvest_month,
            expected_per_quintal=None,
            low_per_quintal=msp_floor,
            high_per_quintal=None,
            msp_floor_per_quintal=msp_floor,
            current_per_quintal=current_price,
            basis="msp_floor",
            observations_used=len(harvest_month_history),
            explanation=explanation,
            explanation_code=explanation_code,
            explanation_params=explanation_params,
            below_msp_by=gap,
        )

    if current_price is not None:
        return PriceOutlook(
            harvest_month=harvest_month,
            expected_per_quintal=None,
            low_per_quintal=None,
            high_per_quintal=None,
            msp_floor_per_quintal=None,
            current_per_quintal=current_price,
            basis="current_only",
            observations_used=len(harvest_month_history),
            explanation=(
                f"Rs {current_price}/quintal is today's mandi price. This crop has no "
                f"support price, and there is not enough history to project {month_name} "
                "— prices could move either way before you sell."
            ),
            explanation_code="current_only",
            explanation_params={"price": current_price, "month": _month_term(harvest_month)},
        )

    return PriceOutlook(
        harvest_month=harvest_month,
        expected_per_quintal=None,
        low_per_quintal=None,
        high_per_quintal=None,
        msp_floor_per_quintal=None,
        current_per_quintal=None,
        basis="none",
        observations_used=0,
        explanation="No price information is available for this crop.",
        explanation_code="none",
    )
