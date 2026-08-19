"""What would have to change for a different answer.

The reasons already say WHY a crop scored as it did. A counterfactual answers
the question a farmer actually asks next: "so what would I have to fix?"

Why this is honest here and would not be with a learned model: the ranker is a
weighted sum of independent factor scores, so we can re-score with one input
perturbed and read the true new value. This is not an approximation of the
model's behaviour — it IS the model, run again. A SHAP explanation over a
gradient-boosted tree is an estimate; this is exact.

Two kinds are produced:

  threshold  — the input value at which this crop's score crosses a rank
               boundary. "At pH 6.5 groundnut moves ahead of sorghum."
  limiting   — the single factor costing the most score right now, with what
               it would be worth to fix.

Two rules keep the output honest, and both were learned from wrong answers the
first version produced:

  1. THIS crop's own score must improve. A rank can rise because a rival fell,
     and the search happily found those: chickpea is a legume, so lowering soil
     nitrogen leaves it untouched while hurting the cereals around it, and the
     tool cheerfully advised reducing nitrogen. Ranks are relative; advice must
     be about the crop in front of the farmer.

  2. The gain must clear a threshold. A rank flip from a 0.1 pH change between
     two crops scoring 0.001 apart is a coin toss, not a lever.

Anything that cannot be expressed as a real, reachable change is not offered.
Telling a farmer to lower their soil pH by two points is not advice either.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Sequence

from services.ml.types import Constraints, CropSpec, RankingInput, ScoredCrop

# Inputs a farmer can plausibly act on, and the realistic bounds of doing so.
# Temperature and rainfall are not here: you cannot amend the climate, and
# suggesting otherwise would be noise dressed as advice.
ACTIONABLE = {
    "soil_ph": {
        "label": "soil pH",
        "unit": "",
        # Liming raises pH; gypsum or sulphur lowers it. Both are slow and
        # bounded — a shift of more than about 1.0 in a season is not real.
        "max_change": 1.0,
        "step": 0.1,
    },
    "nitrogen": {
        "label": "available nitrogen",
        "unit": " kg/ha",
        # A single fertiliser application, not a soil transformation.
        "max_change": 120.0,
        "step": 10.0,
    },
    "irrigation": {
        "label": "water source",
        "unit": "",
        "max_change": None,  # categorical
        "step": None,
    },
}

IRRIGATION_LADDER = ["rainfed", "canal", "tubewell", "drip"]

# Below this the "improvement" is numerical noise between near-tied crops.
MIN_SCORE_GAIN = 0.02


@dataclass(frozen=True)
class Attribution:
    """How much each factor contributed to this crop's score.

    For a weighted sum this is not an approximation of a Shapley value — it IS
    the Shapley value. Each factor's contribution to a linear model is exactly
    its weighted share, so the numbers add to the score with nothing left over.
    A tree-ensemble SHAP plot is an estimate; this is arithmetic.

    `headroom` is the mirror: score this factor is leaving on the table.
    """

    factor: str
    contribution: float
    headroom: float
    score: float
    impact: str
    detail: str
    """English, from the ranker. Localised client-side via `code`."""

    code: str = ""
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Counterfactual:
    factor: str
    kind: str
    """threshold | limiting"""

    current_value: str
    target_value: str | None
    score_gain: float
    rank_gain: int
    message: str
    """English. Localised client-side from `kind` plus `params`."""

    params: dict = field(default_factory=dict)


def attribute(scored: ScoredCrop) -> list[Attribution]:
    """Break a score into per-factor contributions, largest first."""
    total_weight = sum(factor.weight for factor in scored.factors) or 1.0

    rows = [
        Attribution(
            factor=factor.factor,
            contribution=round(factor.score * factor.weight / total_weight, 4),
            headroom=round((1.0 - factor.score) * factor.weight / total_weight, 4),
            score=round(factor.score, 3),
            impact=factor.impact,
            detail=factor.detail,
            code=factor.code,
            params=factor.params,
        )
        for factor in scored.factors
    ]
    rows.sort(key=lambda row: -row.contribution)
    return rows


def _rank_of(crop_code: str, ranked: Sequence[ScoredCrop]) -> int:
    for index, scored in enumerate(ranked, start=1):
        if scored.crop_code == crop_code:
            return index
    return len(ranked) + 1


def find_counterfactuals(
    ranker,
    conditions: RankingInput,
    candidates: Sequence[CropSpec],
    constraints: Constraints,
    crop_code: str,
    max_results: int = 2,
) -> list[Counterfactual]:
    """Re-score with one input changed at a time and report what actually moves.

    Deliberately brute force. The search space is a handful of factors over a
    dozen steps, so an exhaustive sweep costs microseconds and is exactly right
    rather than approximately right.
    """
    baseline = ranker.rank(conditions, candidates, constraints)
    baseline_rank = _rank_of(crop_code, baseline)
    baseline_score = next(
        (s.score for s in baseline if s.crop_code == crop_code), 0.0
    )

    found: list[Counterfactual] = []

    # --- pH and nitrogen: sweep upward and downward for a rank change ---------
    for factor, spec in ACTIONABLE.items():
        if factor == "irrigation":
            continue

        attribute = "ph" if factor == "soil_ph" else "nitrogen_kg_ha"
        current = getattr(conditions, attribute)
        if current is None:
            continue

        step = float(spec["step"])
        max_change = float(spec["max_change"])
        best: Counterfactual | None = None

        for direction in (1, -1):
            change = step
            while change <= max_change:
                candidate_value = current + direction * change
                if candidate_value < 0:
                    break

                probed = ranker.rank(
                    replace(conditions, **{attribute: candidate_value}),
                    candidates,
                    constraints,
                )
                new_rank = _rank_of(crop_code, probed)
                new_score = next(
                    (s.score for s in probed if s.crop_code == crop_code), 0.0
                )

                # Rule 1 and 2: this crop must actually get better, meaningfully.
                improved = new_score - baseline_score >= MIN_SCORE_GAIN

                if new_rank < baseline_rank and improved:
                    best = Counterfactual(
                        factor=factor,
                        kind="threshold",
                        current_value=f"{current:g}{spec['unit']}",
                        target_value=f"{candidate_value:g}{spec['unit']}",
                        score_gain=round(new_score - baseline_score, 3),
                        rank_gain=baseline_rank - new_rank,
                        params={
                            "label": factor,
                            "target": f"{candidate_value:g}{spec['unit']}",
                            "current": f"{current:g}{spec['unit']}",
                            "places": baseline_rank - new_rank,
                        },
                        message=(
                            f"At {spec['label']} {candidate_value:g}{spec['unit']} "
                            f"instead of {current:g}{spec['unit']}, this moves up "
                            f"{baseline_rank - new_rank} place"
                            f"{'s' if baseline_rank - new_rank > 1 else ''}."
                        ),
                    )
                    break
                change += step
            if best is not None:
                break

        if best is not None:
            found.append(best)

    # --- irrigation: would a better water source change the order? -----------
    current_irrigation = conditions.irrigation
    if current_irrigation in IRRIGATION_LADDER:
        start = IRRIGATION_LADDER.index(current_irrigation)
        for better in IRRIGATION_LADDER[start + 1 :]:
            probed = ranker.rank(
                replace(conditions, irrigation=better), candidates, constraints
            )
            new_rank = _rank_of(crop_code, probed)
            new_score = next((s.score for s in probed if s.crop_code == crop_code), 0.0)

            if new_rank < baseline_rank and new_score - baseline_score >= MIN_SCORE_GAIN:
                found.append(
                    Counterfactual(
                        factor="irrigation",
                        kind="threshold",
                        current_value=current_irrigation,
                        target_value=better,
                        score_gain=round(new_score - baseline_score, 3),
                        rank_gain=baseline_rank - new_rank,
                        params={
                            "target": better,
                            "current": current_irrigation,
                            "places": baseline_rank - new_rank,
                        },
                        message=(
                            f"With {better} irrigation instead of {current_irrigation}, "
                            f"this moves up {baseline_rank - new_rank} place"
                            f"{'s' if baseline_rank - new_rank > 1 else ''}."
                        ),
                    )
                )
                break

    # --- nothing moved the rank: name the biggest drag instead ---------------
    if not found:
        scored = next((s for s in baseline if s.crop_code == crop_code), None)
        if scored is not None and scored.factors:
            # Weighted shortfall: how much score each factor is leaving behind.
            worst = max(scored.factors, key=lambda f: (1.0 - f.score) * f.weight)
            shortfall = round((1.0 - worst.score) * worst.weight, 3)
            if shortfall > 0.01:
                found.append(
                    Counterfactual(
                        factor=worst.factor,
                        kind="limiting",
                        current_value="",
                        target_value=None,
                        score_gain=shortfall,
                        rank_gain=0,
                        params={
                            "factor": worst.factor,
                            "shortfall": round(shortfall, 2),
                        },
                        message=(
                            f"Nothing you can realistically change moves this crop up "
                            f"the list. Its biggest limit is {worst.factor.replace('_', ' ')}, "
                            f"costing about {shortfall:.2f} of its score."
                        ),
                    )
                )

    # --- what would COST it its place ----------------------------------------
    # For a crop already at or near the top, "how could this improve" is close
    # to meaningless. The useful question is what it depends on: which single
    # change would drop it. That is the honest fragility statement.
    for factor, spec in ACTIONABLE.items():
        if factor == "irrigation" or len(found) >= max_results + 1:
            continue

        attribute_name = "ph" if factor == "soil_ph" else "nitrogen_kg_ha"
        current = getattr(conditions, attribute_name)
        if current is None:
            continue

        step = float(spec["step"])
        max_change = float(spec["max_change"])

        for direction in (1, -1):
            change = step
            while change <= max_change:
                candidate_value = current + direction * change
                if candidate_value < 0:
                    break

                probed = ranker.rank(
                    replace(conditions, **{attribute_name: candidate_value}),
                    candidates,
                    constraints,
                )
                new_rank = _rank_of(crop_code, probed)

                if new_rank > baseline_rank:
                    found.append(
                        Counterfactual(
                            factor=factor,
                            kind="fragility",
                            current_value=f"{current:g}{spec['unit']}",
                            target_value=f"{candidate_value:g}{spec['unit']}",
                            score_gain=0.0,
                            rank_gain=baseline_rank - new_rank,
                            params={
                                "label": factor,
                                "target": f"{candidate_value:g}{spec['unit']}",
                                "current": f"{current:g}{spec['unit']}",
                                "places": new_rank - baseline_rank,
                            },
                            message=(
                                f"This depends on your {spec['label']}. At "
                                f"{candidate_value:g}{spec['unit']} instead of "
                                f"{current:g}{spec['unit']}, it would drop "
                                f"{new_rank - baseline_rank} place"
                                f"{'s' if new_rank - baseline_rank > 1 else ''}."
                            ),
                        )
                    )
                    break
                change += step
            else:
                continue
            break

    # Improvements first, then fragility, then the limiting note.
    order = {"threshold": 0, "fragility": 1, "limiting": 2}
    found.sort(key=lambda c: (order.get(c.kind, 3), -c.rank_gain, -c.score_gain))
    return found[: max_results + 2]
