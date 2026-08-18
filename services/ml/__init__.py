"""Ranking and forecasting.

    RulesRanker().rank(conditions, candidates, constraints) -> list[ScoredCrop]
    project_yield(crop, score, conditions) -> YieldForecast
    project_price(crop) -> int | None

Everything here is a pure function of its arguments. No I/O, no database, no
network - which is what makes it testable without any of those things.
"""

from services.ml.forecaster import YieldForecast, project_price, project_yield
from services.ml.ranker import Ranker, RulesRanker, load_weights
from services.ml.types import (
    Confidence,
    Constraints,
    CropSpec,
    DateWindow,
    FactorScore,
    RankingInput,
    Risk,
    ScoredCrop,
)

__all__ = [
    "Ranker",
    "RulesRanker",
    "load_weights",
    "project_yield",
    "project_price",
    "YieldForecast",
    "CropSpec",
    "RankingInput",
    "Constraints",
    "ScoredCrop",
    "FactorScore",
    "DateWindow",
    "Risk",
    "Confidence",
]
