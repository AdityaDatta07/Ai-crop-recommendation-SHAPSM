"""Domain types for the ranking and forecasting service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Sequence

Season = Literal["kharif", "rabi", "zaid"]
Irrigation = Literal["rainfed", "canal", "tubewell", "drip"]
Impact = Literal["positive", "neutral", "negative"]
Confidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class Risk:
    type: str
    name: str
    severity: str


@dataclass(frozen=True)
class DateWindow:
    start: str  # MM-DD in the reference file; resolved to ISO dates by the caller
    end: str


@dataclass(frozen=True)
class CropSpec:
    """One crop's agronomic profile, straight from data/reference/crops.yaml."""

    crop_code: str
    name: str
    name_hi: str | None
    category: str
    seasons: tuple[str, ...]
    ph_optimal: tuple[float, float]
    ph_absolute: tuple[float, float]
    temp_optimal_c: tuple[float, float]
    temp_absolute_c: tuple[float, float]
    rainfall_mm: tuple[float, float]
    irrigation_need: str
    texture_preferred: tuple[str, ...]
    nitrogen_demand: str
    legume: bool
    duration_days: int
    sowing_window: DateWindow
    varieties: tuple[str, ...]
    risks: tuple[Risk, ...]
    family: str = ""
    """Botanical family, for rotation.

    Coarser groupings will not do. The display categories file groundnut and
    soybean as oilseeds and both are legumes — which is precisely the fact
    rotation turns on.
    """

    # Economics, carried alongside so the market_price factor can be scored.
    price_per_quintal: int | None = None
    cost_a2fl_per_quintal: int | None = None
    yield_kg_per_ha: float | None = None

    #: Crop name in every language the app speaks, keyed by locale code.
    #:
    #: `name_hi` above is kept only because the frozen v1 contract exposes it
    #: as its own field. New languages go here rather than becoming a sixth
    #: scalar, so adding one is a data change and not a schema change.
    names: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FactorScore:
    factor: str
    score: float          # 0..1
    weight: float
    impact: Impact
    detail: str
    """English sentence. Kept as the fallback when a client has no translation."""

    code: str = ""
    """Stable identifier for this exact message, e.g. "ph_inside_band".

    The API cannot render Hindi without duplicating the frontend's translation
    files in Python, so it emits a code and the values to slot into it. The
    client already has a dictionary; it renders. One place for translations,
    and `detail` still works for any client that has none.
    """

    params: dict = field(default_factory=dict)

    estimated: bool = False
    """True when the score is a stand-in rather than a reading.

    An unpriceable crop still scores on market_price, but that score is a
    penalty we chose, not a margin we computed. Flagging it keeps it out of the
    confidence numerator, so a crop we know less about does not come back
    looking more certain.
    """


@dataclass(frozen=True)
class ScoredCrop:
    crop_code: str
    score: float
    confidence: Confidence
    factors: tuple[FactorScore, ...]
    weight_coverage: float

    @property
    def reasons(self) -> tuple[FactorScore, ...]:
        """The 2-4 factors worth showing, per the API contract.

        A farmer needs to know what makes this a good idea and what will bite
        them - not a ranked dump of everything the model looked at. So: the two
        strongest positives, the two strongest negatives, topped up with
        neutrals only if that leaves fewer than two reasons.

        Selection is by position, not by value equality, so two factors that
        happen to score identically cannot collapse into one.
        """
        if not self.factors:
            return ()

        order = sorted(
            range(len(self.factors)),
            key=lambda i: self.factors[i].score * self.factors[i].weight,
            reverse=True,
        )
        positives = [i for i in order if self.factors[i].impact == "positive"]
        neutrals = [i for i in order if self.factors[i].impact == "neutral"]

        # Negatives are ranked by what they COST, not by what they contribute.
        #
        # score x weight ranks a factor by how much it adds. For a positive
        # that is the right question. For a negative the right question is how
        # much it takes away, which is weight x (1 - score) — and the two
        # disagree. A rotation factor scoring 0.10 at weight 0.08 contributes
        # almost nothing (0.008) yet costs more than a factor scoring 0.44 at
        # the same weight. Ranked by contribution, the worse problem was
        # reported second and could fall off the end of a four-reason list.
        negatives = sorted(
            (i for i in range(len(self.factors)) if self.factors[i].impact == "negative"),
            key=lambda i: self.factors[i].weight * (1 - self.factors[i].score),
            reverse=True,
        )

        picked: set[int] = set(positives[:2]) | set(negatives[:2])

        # The contract requires at least 2 reasons; top up from neutrals, then
        # from whatever is left, before giving up.
        for pool in (neutrals, order):
            for index in pool:
                if len(picked) >= 2:
                    break
                picked.add(index)

        return tuple(self.factors[i] for i in order if i in picked)[:4]


@dataclass(frozen=True)
class RankingInput:
    """Everything the ranker is allowed to see."""

    ph: float | None = None
    texture: str | None = None
    nitrogen_kg_ha: float | None = None
    avg_temp_c: float | None = None
    season_rainfall_mm: float | None = None
    annual_rainfall_mm: float | None = None
    irrigation: str = "rainfed"
    previous_crop: str | None = None
    """What the farmer says grew here last season. Optional, and its absence
    must not be treated as a gap in the field data — see RulesRanker.rank."""

    data_completeness: float = 1.0


@dataclass(frozen=True)
class Constraints:
    exclude_crops: Sequence[str] = field(default_factory=tuple)
    max_input_cost: int | None = None
    organic_only: bool = False
