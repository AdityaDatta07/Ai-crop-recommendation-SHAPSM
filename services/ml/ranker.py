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

from services.ml import rotation as rotation_rules
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

    def _factors(
        self,
        conditions: RankingInput,
        crop: CropSpec,
        previous: CropSpec | None = None,
    ) -> list[FactorScore]:
        priced = scoring.is_priced(crop.price_per_quintal, crop.cost_a2fl_per_quintal)
        rotation_score, rotation_code, rotation_params = rotation_rules.score(previous, crop)

        raw: list[tuple[str, float | None, tuple[str, str, dict], bool]] = [
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
            (
                "rotation",
                rotation_score,
                self._rotation_detail(rotation_code, rotation_params),
                False,
            ),
        ]

        factors: list[FactorScore] = []
        for name, score, (detail, code, params), estimated in raw:
            if score is None:
                continue  # Missing field data: weight is dropped, not scored zero.
            factors.append(
                FactorScore(
                    factor=name,
                    score=score,
                    weight=self.weights.get(name, 0.0),
                    impact=_impact(score),
                    detail=detail,
                    code=code,
                    params=params,
                    estimated=estimated,
                )
            )
        return factors

    # ------------------------------------------------------- reason wording

    def _ph_detail(self, c: RankingInput, crop: CropSpec) -> tuple[str, str, dict]:
        low, high = crop.ph_optimal
        if c.ph is None:
            return ("Soil pH unavailable.", "ph_unavailable", {})
        if low <= c.ph <= high:
            return (
                f"pH {c.ph} sits inside {crop.name.lower()}'s preferred {low}-{high} band.",
                "ph_inside_band",
                {"ph": c.ph, "crop": crop.name.lower(), "low": low, "high": high},
            )
        acidic = c.ph < low
        return (
            f"pH {c.ph} is more {'acidic' if acidic else 'alkaline'} than the preferred "
            f"{low}-{high} band, which can limit nutrient uptake.",
            "ph_too_acidic" if acidic else "ph_too_alkaline",
            {"ph": c.ph, "low": low, "high": high},
        )

    def _temp_detail(self, c: RankingInput, crop: CropSpec) -> tuple[str, str, dict]:
        low, high = crop.temp_optimal_c
        if c.avg_temp_c is None:
            return ("Temperature data unavailable.", "temp_unavailable", {})
        params = {"temp": c.avg_temp_c, "low": low, "high": high}
        if low <= c.avg_temp_c <= high:
            return (
                f"Average {c.avg_temp_c} C is within the ideal {low}-{high} C range.",
                "temp_ideal",
                params,
            )
        cooler = c.avg_temp_c < low
        return (
            f"Average {c.avg_temp_c} C is {'cooler' if cooler else 'warmer'} than the "
            f"ideal {low}-{high} C range.",
            "temp_cooler" if cooler else "temp_warmer",
            params,
        )

    def _rain_detail(self, c: RankingInput, crop: CropSpec) -> tuple[str, str, dict]:
        low, high = crop.rainfall_mm
        if c.season_rainfall_mm is None:
            return ("Seasonal rainfall data unavailable.", "rain_unavailable", {})
        if c.season_rainfall_mm >= low:
            return (
                f"Seasonal rainfall of {c.season_rainfall_mm:.0f} mm meets the "
                f"{low:.0f}-{high:.0f} mm need.",
                "rain_sufficient",
                {"rain": round(c.season_rainfall_mm), "low": round(low), "high": round(high)},
            )
        shortfall = round(low - c.season_rainfall_mm)
        if c.irrigation == "rainfed":
            return (
                f"Rainfall is about {shortfall} mm short of the {low:.0f} mm this crop "
                "needs, with no irrigation to make it up.",
                "rain_short_rainfed",
                {"shortfall": shortfall, "needed": round(low)},
            )
        return (
            f"Rainfall is about {shortfall} mm short; your {c.irrigation} supply would "
            "need to cover the gap.",
            "rain_short_irrigated",
            {"shortfall": shortfall, "source": c.irrigation},
        )

    def _texture_detail(self, c: RankingInput, crop: CropSpec) -> tuple[str, str, dict]:
        if c.texture is None:
            return ("Soil texture unavailable.", "texture_unavailable", {})
        preferred = ", ".join(crop.texture_preferred)
        params = {"texture": c.texture.capitalize(), "preferred": preferred}
        if c.texture.lower() in [t.lower() for t in crop.texture_preferred]:
            return (
                f"{c.texture.capitalize()} soil is well suited; this crop prefers {preferred}.",
                "texture_suited",
                params,
            )
        return (
            f"{c.texture.capitalize()} soil is workable but this crop prefers {preferred}.",
            "texture_workable",
            params,
        )

    def _nitrogen_detail(self, c: RankingInput, crop: CropSpec) -> tuple[str, str, dict]:
        if crop.legume:
            return (
                "Fixes its own nitrogen and leaves the soil better for the next crop.",
                "nitrogen_legume",
                {},
            )
        if c.nitrogen_kg_ha is None:
            return ("Soil nitrogen unavailable.", "nitrogen_unavailable", {})
        required = scoring.NITROGEN_BANDS.get(crop.nitrogen_demand, 220.0)
        params = {"available": round(c.nitrogen_kg_ha), "required": round(required)}
        if c.nitrogen_kg_ha >= required:
            return (
                f"Available nitrogen ({c.nitrogen_kg_ha:.0f} kg/ha) covers this crop's needs.",
                "nitrogen_sufficient",
                params,
            )
        return (
            f"Available nitrogen ({c.nitrogen_kg_ha:.0f} kg/ha) is below the "
            f"{required:.0f} kg/ha this crop wants; expect to make it up with fertiliser.",
            "nitrogen_short",
            params,
        )

    def _irrigation_detail(self, c: RankingInput, crop: CropSpec) -> tuple[str, str, dict]:
        if crop.irrigation_need == "high" and c.irrigation == "rainfed":
            return (
                "This crop needs reliable irrigation and you have reported rainfed land only.",
                "irrigation_needs_more",
                {},
            )
        if crop.irrigation_need == "low":
            return (
                "Tolerates limited water, so it suits a season with little to spare.",
                "irrigation_tolerant",
                {},
            )
        return (
            f"Water requirement is {crop.irrigation_need}; your {c.irrigation} supply "
            "is adequate.",
            "irrigation_adequate",
            {"need": crop.irrigation_need, "source": c.irrigation},
        )

    def _market_detail(self, crop: CropSpec) -> tuple[str, str, dict]:
        if crop.price_per_quintal is None or crop.cost_a2fl_per_quintal is None:
            return (
                "No support price published for this crop; margin depends entirely on "
                "the mandi.",
                "market_no_msp",
                {},
            )
        margin = crop.price_per_quintal - crop.cost_a2fl_per_quintal
        return (
            f"MSP of Rs {crop.price_per_quintal}/quintal against a published cost of "
            f"Rs {crop.cost_a2fl_per_quintal}/quintal leaves about Rs {margin}/quintal.",
            "market_msp_margin",
            {
                "price": crop.price_per_quintal,
                "cost": crop.cost_a2fl_per_quintal,
                "margin": margin,
            },
        )

    # --------------------------------------------------------------- rotation

    #: English fallbacks for the rotation codes. The codes and params come from
    #: services/ml/rotation.py; this is only the wording, kept beside the other
    #: reason wording so a reader finds all of it in one place.
    ROTATION_ENGLISH = {
        "rotation_same_crop": "Growing {crop} again in the same ground builds up its own pests and diseases.",
        "rotation_after_legume": "Follows {previous}, a legume, which leaves nitrogen behind for {crop}.",
        "rotation_same_family": "Same plant family as {previous}, so the two share diseases.",
        "rotation_same_family_pest": "Same plant family as {previous}, and both carry {pest}.",
        "rotation_shared_pest": "Both this crop and {previous} carry {pest}, which can carry over in the soil.",
        "rotation_legume_next": "A legume after {previous}: it breaks the disease cycle and fixes its own nitrogen.",
        "rotation_both_hungry": "Both this crop and {previous} are hungry for nitrogen, one straight after the other.",
        "rotation_clean_break": "A clean break from {previous}: different family, no shared pests.",
        "rotation_unknown": "No previous crop given.",
    }

    def _rotation_detail(self, code: str, params: dict) -> tuple[str, str, dict]:
        template = self.ROTATION_ENGLISH.get(code, "")
        try:
            english = template.format(**params)
        except KeyError:
            english = template
        return english, code, params

    # ------------------------------------------------------------------ rank

    def rank(
        self,
        conditions: RankingInput,
        candidates: Sequence[CropSpec],
        constraints: Constraints,
    ) -> list[ScoredCrop]:
        excluded = {code.upper() for code in constraints.exclude_crops}

        previous = None
        if conditions.previous_crop:
            wanted = conditions.previous_crop.upper()
            previous = next((c for c in candidates if c.crop_code == wanted), None)

        # Confidence measures how much we know about the FIELD. Rotation is the
        # one factor that depends on an optional question instead, so when the
        # farmer skips it the weight leaves the denominator too. Otherwise
        # declining an optional dropdown would silently lower the confidence of
        # every crop, which reads as "we trust this field less" when the truth
        # is only "you did not tell us one thing".
        total_weight = sum(
            weight
            for name, weight in self.weights.items()
            if previous is not None or name != "rotation"
        ) or 1.0

        scored: list[ScoredCrop] = []
        for crop in candidates:
            if crop.crop_code in excluded:
                continue

            factors = self._factors(conditions, crop, previous)
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
