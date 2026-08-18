"""Crop ranking.

v1 is rules-based. Two properties this buys, both of which matter more than
accuracy right now:

  - Every score decomposes into the named factors the API contract requires in
    `reasons`. Explainability is structural, not bolted on afterwards.
  - No training data, so there is no dataset provenance argument to lose.

The Protocol below is the seam for a learned model. A future ModelRanker
implements the same interface and produces SHAP values to populate `reasons`;
the orchestrator does not change. See docs/ai-design.md.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol, Sequence

import yaml

from services.ml import scoring
from services.ml.types import (
    Confidence,
    Constraints,
    CropSpec,
    FactorScore,
    Impact,
    RankingInput,
    ScoredCrop,
)

logger = logging.getLogger(__name__)

WEIGHTS_PATH = Path(__file__).resolve().parent / "config" / "weights.yaml"

# Above this a factor reads as a reason to plant; below it, a reason not to.
POSITIVE_THRESHOLD = 0.75
NEGATIVE_THRESHOLD = 0.45


class Ranker(Protocol):
    """The interface the orchestrator depends on. Implementations are swappable."""

    def rank(
        self,
        conditions: RankingInput,
        candidates: Sequence[CropSpec],
        constraints: Constraints,
    ) -> list[ScoredCrop]: ...


def load_weights(path: Path = WEIGHTS_PATH) -> dict[str, float]:
    with path.open(encoding="utf-8") as handle:
        return dict(yaml.safe_load(handle)["weights"])


def _impact(score: float) -> Impact:
    if score >= POSITIVE_THRESHOLD:
        return "positive"
    if score < NEGATIVE_THRESHOLD:
        return "negative"
    return "neutral"


def _confidence(data_completeness: float, weight_coverage: float) -> Confidence:
    """Per the contract, confidence is derived from how much input we actually had.

    Both terms matter: complete soil data is no use if the crop has no price, and
    a fully weighted score built on 40% of the inputs is not trustworthy either.
    """
    effective = data_completeness * weight_coverage
    if effective >= 0.80:
        return "high"
    if effective >= 0.50:
        return "medium"
    return "low"


class RulesRanker:
    """Scores each factor against published ranges, then combines by weight."""

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = weights if weights is not None else load_weights()

    # ---------------------------------------------------------------- factors

    def _factors(self, conditions: RankingInput, crop: CropSpec) -> list[FactorScore]:
        priced = scoring.is_priced(crop.price_per_quintal, crop.cost_a2fl_per_quintal)

        raw: list[tuple[str, float | None, str, bool]] = [
            (
                "soil_ph",
                scoring.score_ph(conditions.ph, crop.ph_optimal, crop.ph_absolute),
                self._ph_detail(conditions, crop),
                False,
            ),
            (
                "temperature",
                scoring.score_temperature(
                    conditions.avg_temp_c, crop.temp_optimal_c, crop.temp_absolute_c
                ),
                self._temp_detail(conditions, crop),
                False,
            ),
            (
                "rainfall",
                scoring.score_rainfall(
                    conditions.season_rainfall_mm, crop.rainfall_mm, conditions.irrigation
                ),
                self._rain_detail(conditions, crop),
                False,
            ),
            (
                "soil_texture",
                scoring.score_texture(conditions.texture, crop.texture_preferred),
                self._texture_detail(conditions, crop),
                False,
            ),
            (
                "nitrogen",
                scoring.score_nitrogen(
                    conditions.nitrogen_kg_ha, crop.nitrogen_demand, crop.legume
                ),
                self._nitrogen_detail(conditions, crop),
                False,
            ),
            (
                "irrigation",
                scoring.score_irrigation(conditions.irrigation, crop.irrigation_need),
                self._irrigation_detail(conditions, crop),
                False,
            ),
            (
                "market_price",
                scoring.score_market(crop.price_per_quintal, crop.cost_a2fl_per_quintal),
                self._market_detail(crop),
                not priced,
            ),
        ]

        factors: list[FactorScore] = []
        for name, score, detail, estimated in raw:
            if score is None:
                continue  # Missing field data: weight is dropped, not scored zero.
            factors.append(
                FactorScore(
                    factor=name,
                    score=score,
                    weight=self.weights.get(name, 0.0),
                    impact=_impact(score),
                    detail=detail,
                    estimated=estimated,
                )
            )
        return factors

    # ------------------------------------------------------- reason wording

    def _ph_detail(self, c: RankingInput, crop: CropSpec) -> str:
        low, high = crop.ph_optimal
        if c.ph is None:
            return "Soil pH unavailable."
        if low <= c.ph <= high:
            return f"pH {c.ph} sits inside {crop.name.lower()}'s preferred {low}-{high} band."
        direction = "acidic" if c.ph < low else "alkaline"
        return (
            f"pH {c.ph} is more {direction} than the preferred {low}-{high} band, "
            "which can limit nutrient uptake."
        )

    def _temp_detail(self, c: RankingInput, crop: CropSpec) -> str:
        low, high = crop.temp_optimal_c
        if c.avg_temp_c is None:
            return "Temperature data unavailable."
        if low <= c.avg_temp_c <= high:
            return f"Average {c.avg_temp_c} C is within the ideal {low}-{high} C range."
        side = "cooler" if c.avg_temp_c < low else "warmer"
        return f"Average {c.avg_temp_c} C is {side} than the ideal {low}-{high} C range."

    def _rain_detail(self, c: RankingInput, crop: CropSpec) -> str:
        low, high = crop.rainfall_mm
        if c.season_rainfall_mm is None:
            return "Seasonal rainfall data unavailable."
        if c.season_rainfall_mm >= low:
            return f"Seasonal rainfall of {c.season_rainfall_mm:.0f} mm meets the {low:.0f}-{high:.0f} mm need."
        shortfall = low - c.season_rainfall_mm
        if c.irrigation == "rainfed":
            return (
                f"Rainfall is about {shortfall:.0f} mm short of the {low:.0f} mm this crop needs, "
                "with no irrigation to make it up."
            )
        return (
            f"Rainfall is about {shortfall:.0f} mm short; your {c.irrigation} supply "
            "would need to cover the gap."
        )

    def _texture_detail(self, c: RankingInput, crop: CropSpec) -> str:
        if c.texture is None:
            return "Soil texture unavailable."
        preferred = ", ".join(crop.texture_preferred)
        if c.texture.lower() in [t.lower() for t in crop.texture_preferred]:
            return f"{c.texture.capitalize()} soil is well suited; this crop prefers {preferred}."
        return f"{c.texture.capitalize()} soil is workable but this crop prefers {preferred}."

    def _nitrogen_detail(self, c: RankingInput, crop: CropSpec) -> str:
        if crop.legume:
            return "Fixes its own nitrogen and leaves the soil better for the next crop."
        if c.nitrogen_kg_ha is None:
            return "Soil nitrogen unavailable."
        required = scoring.NITROGEN_BANDS.get(crop.nitrogen_demand, 220.0)
        if c.nitrogen_kg_ha >= required:
            return f"Available nitrogen ({c.nitrogen_kg_ha:.0f} kg/ha) covers this crop's needs."
        return (
            f"Available nitrogen ({c.nitrogen_kg_ha:.0f} kg/ha) is below the "
            f"{required:.0f} kg/ha this crop wants; expect to make it up with fertiliser."
        )

    def _irrigation_detail(self, c: RankingInput, crop: CropSpec) -> str:
        if crop.irrigation_need == "high" and c.irrigation == "rainfed":
            return "This crop needs reliable irrigation and you have reported rainfed land only."
        if crop.irrigation_need == "low":
            return "Tolerates limited water, so it suits a season with little to spare."
        return f"Water requirement is {crop.irrigation_need}; your {c.irrigation} supply is adequate."

    def _market_detail(self, crop: CropSpec) -> str:
        if crop.price_per_quintal is None or crop.cost_a2fl_per_quintal is None:
            return "No support price published for this crop; margin depends entirely on the mandi."
        margin = crop.price_per_quintal - crop.cost_a2fl_per_quintal
        return (
            f"MSP of Rs {crop.price_per_quintal}/quintal against a published cost of "
            f"Rs {crop.cost_a2fl_per_quintal}/quintal leaves about Rs {margin}/quintal."
        )

    # ------------------------------------------------------------------ rank

    def rank(
        self,
        conditions: RankingInput,
        candidates: Sequence[CropSpec],
        constraints: Constraints,
    ) -> list[ScoredCrop]:
        excluded = {code.upper() for code in constraints.exclude_crops}
        total_weight = sum(self.weights.values()) or 1.0

        scored: list[ScoredCrop] = []
        for crop in candidates:
            if crop.crop_code in excluded:
                continue

            factors = self._factors(conditions, crop)
            scored_weight = sum(f.weight for f in factors)
            if scored_weight <= 0:
                logger.warning("No scorable factors for %s; skipping", crop.crop_code)
                continue

            # Renormalise over the factors we could actually score, so missing
            # FIELD data costs confidence rather than points. Estimated factors
            # are included here on purpose: an unpriceable crop should carry its
            # penalty into the score, not have it normalised away.
            weighted = sum(f.score * f.weight for f in factors) / scored_weight

            # Confidence, though, counts only the factors backed by real data.
            # Fewer facts must never read as more certainty.
            measured_weight = sum(f.weight for f in factors if not f.estimated)
            coverage = measured_weight / total_weight

            scored.append(
                ScoredCrop(
                    crop_code=crop.crop_code,
                    score=round(weighted, 4),
                    confidence=_confidence(conditions.data_completeness, coverage),
                    factors=tuple(factors),
                    weight_coverage=round(coverage, 4),
                )
            )

        # Ties broken by crop_code so the ordering is stable across runs - a
        # demo that reshuffles between refreshes looks broken.
        scored.sort(key=lambda s: (-s.score, s.crop_code))
        return scored
