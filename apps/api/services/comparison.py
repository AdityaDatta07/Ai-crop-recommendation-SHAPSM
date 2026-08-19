"""Last season's crop against this season's recommendation.

The design decision worth stating: we ask for the crop NAME and nothing else.

The obvious alternative is to ask what they actually earned — their yield, their
costs, their sale price. It is tempting because it would be real data. It is
wrong here for two reasons. It is a form a farmer has to fill in from memory,
which is friction at exactly the moment they want an answer. And it produces a
second source of truth: their remembered figures against our computed ones,
with no way to reconcile a difference.

Instead we value last season's crop the same way we value every candidate — same
field, same soil, same prices, same engine. The comparison is then honest in a
specific way: the ONLY thing that differs between the two sides is the crop. Any
gap is attributable to the choice, not to whose numbers you trust.

What that costs: this is not "what you actually made". It is "what our model
says that crop is worth on this field", which is the right basis for choosing
between two crops and the wrong basis for auditing last year's accounts. The
verdict text says so.
"""

from __future__ import annotations

import logging

from apps.api.schemas import contract as api

logger = logging.getLogger(__name__)


def _side(recommendation: api.Recommendation | None, crop_code: str, name: str) -> api.ComparisonSide:
    if recommendation is None:
        return api.ComparisonSide(crop_code=crop_code, name=name)

    return api.ComparisonSide(
        crop_code=recommendation.crop_code,
        name=recommendation.name,
        rank=recommendation.rank,
        score=recommendation.score,
        net_margin=recommendation.economics.net_margin,
        margin_per_ha=recommendation.economics.margin_per_ha,
        margin_per_acre=recommendation.economics.margin_per_acre,
        expected_yield_t_ha=recommendation.economics.expected_yield_t_ha,
    )


def build_comparison(
    previous: api.Recommendation | None,
    previous_code: str,
    previous_name: str,
    recommended: api.Recommendation,
) -> api.CropComparison:
    """Compare, and say plainly which is better and by how much."""
    previous_side = _side(previous, previous_code, previous_name)
    recommended_side = _side(recommended, recommended.crop_code, recommended.name)

    same = previous_code.upper() == recommended.crop_code.upper()

    if same:
        return api.CropComparison(
            previous=previous_side,
            recommended=recommended_side,
            margin_difference=0,
            rank_difference=0,
            same_crop=True,
            verdict=(
                f"{recommended.name} is what you grew last season and it is still the "
                "best fit for this field. No change needed."
            ),
            verdict_code="same_crop",
            verdict_params={"crop": recommended.name, "crop_code": recommended.crop_code},
        )

    if previous is None:
        return api.CropComparison(
            previous=previous_side,
            recommended=recommended_side,
            same_crop=False,
            verdict=(
                f"{previous_name} is not suited to this field this season, so there is "
                f"nothing to compare against. {recommended.name} is the better choice."
            ),
            verdict_code="previous_unsuited",
            verdict_params={
                "previous": previous_name,
                "previous_code": previous_code,
                "crop": recommended.name,
                "crop_code": recommended.crop_code,
            },
        )

    margin_difference = None
    if (
        previous.economics.net_margin is not None
        and recommended.economics.net_margin is not None
    ):
        margin_difference = recommended.economics.net_margin - previous.economics.net_margin

    rank_difference = (
        previous.rank - recommended.rank
        if previous.rank is not None and recommended.rank is not None
        else None
    )

    # Wording follows the money, because that is what the farmer is deciding on.
    verdict_params: dict = {
        "previous": previous_name,
        "previous_code": previous_code,
        "crop": recommended.name,
        "crop_code": recommended.crop_code,
    }
    if margin_difference is None:
        verdict_code = "better_fit_unpriced"
        verdict = (
            f"{recommended.name} scores better than {previous_name} on this field, but "
            "one of them has no published price so the earnings cannot be compared."
        )
    elif margin_difference > 0:
        verdict_code = "switch_pays_more"
        verdict_params["amount"] = margin_difference
        verdict = (
            f"Switching from {previous_name} to {recommended.name} is worth about "
            f"Rs {margin_difference:,} more on this plot, on our figures for both."
        )
    elif margin_difference < 0:
        # The recommendation is agronomically better but pays less. Say so
        # rather than burying it — a farmer may reasonably still choose income.
        verdict_code = "switch_pays_less"
        verdict_params["amount"] = abs(margin_difference)
        verdict = (
            f"{recommended.name} suits this field better agronomically, but "
            f"{previous_name} would earn about Rs {abs(margin_difference):,} more on "
            "current prices. Weigh the risk against the return."
        )
    else:
        verdict_code = "level_on_money"
        verdict = (
            f"{recommended.name} and {previous_name} come out about level on money. "
            f"{recommended.name} is the better agronomic fit."
        )

    return api.CropComparison(
        previous=previous_side,
        recommended=recommended_side,
        margin_difference=margin_difference,
        rank_difference=rank_difference,
        same_crop=False,
        verdict=verdict,
        verdict_code=verdict_code,
        verdict_params=verdict_params,
    )
