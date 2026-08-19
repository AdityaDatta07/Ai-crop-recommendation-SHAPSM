"""Rotation rules, and the one place confidence could have gone wrong.

The agronomy here is not controversial — wheat after wheat is worse than wheat
after chickpea — so most of these tests pin the ORDERING rather than the exact
numbers, which are expert-set and awaiting the same review as crops.yaml.

The test that matters most is the last class. Rotation is scored from an
OPTIONAL dropdown, and an optional question left blank must not look like
missing knowledge about the field.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app

from services.ml import rotation
from services.ml.types import CropSpec, DateWindow, Risk


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def crop(
    code: str,
    *,
    family: str,
    legume: bool = False,
    nitrogen: str = "medium",
    risks: tuple[Risk, ...] = (),
) -> CropSpec:
    return CropSpec(
        crop_code=code,
        name=code.title(),
        name_hi=None,
        category="test",
        seasons=("rabi",),
        ph_optimal=(6.0, 7.5),
        ph_absolute=(5.0, 8.5),
        temp_optimal_c=(15.0, 25.0),
        temp_absolute_c=(5.0, 35.0),
        rainfall_mm=(300.0, 600.0),
        irrigation_need="medium",
        texture_preferred=("loam",),
        nitrogen_demand=nitrogen,
        legume=legume,
        family=family,
        duration_days=130,
        sowing_window=DateWindow(start="11-01", end="12-01"),
        varieties=(),
        risks=risks,
        price_per_quintal=5000,
        cost_a2fl_per_quintal=2500,
        yield_kg_per_ha=3000.0,
    )


RUST = Risk(type="pest", name="Yellow rust", severity="high")
BLIGHT = Risk(type="disease", name="Late blight", severity="high")

WHEAT = crop("WHEAT", family="poaceae", nitrogen="high", risks=(RUST,))
BARLEY = crop("BARLEY", family="poaceae", risks=(RUST,))
MAIZE = crop("MAIZE", family="poaceae", nitrogen="high")
CHICKPEA = crop("CHICKPEA", family="fabaceae", legume=True, nitrogen="low")
MUSTARD = crop("MUSTARD", family="brassicaceae")
POTATO = crop("POTATO", family="solanaceae", nitrogen="high", risks=(BLIGHT,))
TOMATO = crop("TOMATO", family="solanaceae", risks=(BLIGHT,))


def value(previous, candidate) -> float:
    result, _, _ = rotation.score(previous, candidate)
    return result


class TestTheOrderingIsAgronomicallySane:
    def test_the_same_crop_twice_is_the_worst_case(self):
        repeat = value(WHEAT, WHEAT)
        assert repeat < value(BARLEY, WHEAT)
        assert repeat < value(MUSTARD, WHEAT)
        assert repeat < value(CHICKPEA, WHEAT)

    def test_a_relative_scores_worse_than_a_stranger(self):
        """Wheat and barley share the rusts. Mustard shares nothing with either."""
        assert value(BARLEY, WHEAT) < value(MUSTARD, WHEAT)

    def test_following_a_legume_is_the_best_case(self):
        assert value(CHICKPEA, WHEAT) > value(MUSTARD, WHEAT)
        assert value(CHICKPEA, WHEAT) == pytest.approx(rotation.AFTER_LEGUME)

    def test_planting_a_legume_next_is_rewarded(self):
        """It breaks the cycle and feeds itself, even after an unrelated crop."""
        assert value(MUSTARD, CHICKPEA) > value(MUSTARD, WHEAT)

    def test_two_hungry_crops_in_a_row_score_below_a_clean_break(self):
        assert value(MAIZE, WHEAT) < value(MUSTARD, WHEAT)

    def test_family_matters_more_than_display_category(self):
        """The trap this exists to avoid.

        The display categories file groundnut and soybean as 'oilseed' beside
        mustard. Two of those three are legumes. Rotation that keyed off
        category would call soybean-then-mustard a legume break and
        mustard-then-groundnut nothing special, both backwards.
        """
        groundnut = crop("GROUNDNUT", family="fabaceae", legume=True)
        assert value(groundnut, MUSTARD) == pytest.approx(rotation.AFTER_LEGUME)
        assert value(MUSTARD, groundnut) == pytest.approx(rotation.LEGUME_NEXT)


class TestSharedPestsAreCaught:
    def test_a_shared_disease_is_penalised_across_families(self):
        """Different families can still hand a pathogen to each other."""
        carrier = crop("CARRIER", family="malvaceae", risks=(BLIGHT,))
        assert value(carrier, POTATO) == pytest.approx(rotation.SHARED_PEST)

    def test_a_shared_disease_within_a_family_names_the_pathogen(self):
        _, code, params = rotation.score(POTATO, TOMATO)
        assert code == "rotation_same_family_pest"
        assert params["pest"] == "Late blight"

    def test_only_biological_risks_carry_over(self):
        """A shared market or cost risk is not a soil problem."""
        market_risk = Risk(type="market", name="Price crash", severity="high")
        a = crop("A", family="poaceae", risks=(market_risk,))
        b = crop("B", family="brassicaceae", risks=(market_risk,))
        assert value(a, b) == pytest.approx(rotation.CLEAN_BREAK)


class TestSkippingTheQuestionIsNotAPenalty:
    """The subtle one.

    Rotation comes from an optional dropdown. A farmer who declines it has not
    revealed a gap in their field — they have declined a question. Scoring that
    as missing data would have quietly lowered the confidence of every crop for
    everyone who skipped it, reading as "we trust this field less".
    """

    def test_no_previous_crop_returns_none_not_zero(self):
        result, code, _ = rotation.score(None, WHEAT)
        assert result is None, "a skipped question must not score as a bad rotation"
        assert code == "rotation_unknown"

    def test_confidence_is_unchanged_by_skipping_the_question(self):
        from apps.api.core.reference import load_reference
        from services.ml import Constraints, RankingInput, RulesRanker

        reference = load_reference()
        candidates = reference.crops_for_season("rabi")
        base = dict(
            ph=7.2,
            texture="loam",
            nitrogen_kg_ha=250,
            avg_temp_c=18.0,
            season_rainfall_mm=200.0,
            irrigation="canal",
            data_completeness=1.0,
        )

        asked = RulesRanker().rank(
            RankingInput(**base, previous_crop="CHICKPEA"), candidates, Constraints()
        )
        skipped = RulesRanker().rank(
            RankingInput(**base, previous_crop=None), candidates, Constraints()
        )

        assert skipped[0].confidence == asked[0].confidence
        assert skipped[0].weight_coverage == pytest.approx(asked[0].weight_coverage)

    def test_the_rotation_factor_is_absent_rather_than_low(self):
        from apps.api.core.reference import load_reference
        from services.ml import Constraints, RankingInput, RulesRanker

        reference = load_reference()
        result = RulesRanker().rank(
            RankingInput(ph=7.2, texture="loam", avg_temp_c=18.0, irrigation="canal"),
            reference.crops_for_season("rabi"),
            Constraints(),
        )
        assert all(f.factor != "rotation" for f in result[0].factors)


class TestEveryOutcomeHasAMessage:
    @pytest.mark.parametrize(
        "previous,candidate",
        [
            (WHEAT, WHEAT),
            (CHICKPEA, WHEAT),
            (BARLEY, WHEAT),
            (POTATO, TOMATO),
            (MUSTARD, CHICKPEA),
            (MAIZE, WHEAT),
            (MUSTARD, WHEAT),
            (None, WHEAT),
        ],
    )
    def test_a_code_is_always_returned(self, previous, candidate):
        _, code, params = rotation.score(previous, candidate)
        assert code.startswith("rotation_")
        assert isinstance(params, dict)


class TestTheReasonReachesTheFarmer:
    """A rotation penalty nobody sees is not an explanation.

    Reasons show the two strongest positives and the two strongest negatives.
    Negatives used to be ranked by score x weight — how much they CONTRIBUTE —
    when the question for a negative is how much it COSTS. A rotation factor
    scoring 0.10 at weight 0.08 contributes almost nothing and costs more than
    a factor scoring 0.44 at the same weight, so the worst problem with a
    choice could be ranked last and fall off a four-reason list.
    """

    def test_the_costliest_negative_is_always_shown(self):
        from services.ml.types import FactorScore, ScoredCrop

        factors = (
            # Smallest score x weight, largest actual cost.
            FactorScore("rotation", 0.10, 0.08, "negative", "repeat", "a", {}),
            FactorScore("rainfall", 0.44, 0.18, "negative", "dry", "b", {}),
            FactorScore("nitrogen", 0.40, 0.10, "negative", "low n", "c", {}),
            FactorScore("soil_ph", 0.95, 0.20, "positive", "ph", "d", {}),
            FactorScore("temperature", 0.90, 0.20, "positive", "temp", "e", {}),
        )
        shown = [f.factor for f in ScoredCrop("X", 0.7, "high", factors, 1.0).reasons]
        assert "rotation" in shown

    def test_repeating_a_crop_explains_itself(self):
        """End to end: the penalised crop must carry the reason for it."""
        from apps.api.core.reference import load_reference
        from services.ml import Constraints, RankingInput, RulesRanker

        reference = load_reference()
        ranked = RulesRanker().rank(
            RankingInput(
                ph=7.2,
                texture="loam",
                nitrogen_kg_ha=250,
                avg_temp_c=18.0,
                season_rainfall_mm=200.0,
                irrigation="canal",
                previous_crop="WHEAT",
            ),
            reference.crops_for_season("rabi"),
            Constraints(),
        )
        wheat = next(crop for crop in ranked if crop.crop_code == "WHEAT")
        codes = [reason.code for reason in wheat.reasons]
        assert "rotation_same_crop" in codes


class TestRotationIsVisibleNotJustComputed:
    """A feature the farmer cannot find is a feature that was not shipped.

    Rotation flows into `reasons`, but reasons show only the four strongest
    factors — so a farmer who answered the dropdown often saw no trace of it
    anywhere on the page. Every recommendation now carries its rotation note
    regardless of whether it won a reason slot.
    """

    def _post(self, client, previous=None):
        body = {
            "location": {
                "type": "admin",
                "state_code": "UP",
                "district_code": "UP-LKO",
            },
            "season": "rabi",
            "area_ha": 2.0,
            "irrigation": "canal",
        }
        if previous:
            body["previous_crop"] = previous
        return client.post("/api/v1/recommendations", json=body).json()

    def test_every_recommendation_carries_a_rotation_note(self, client):
        body = self._post(client, "WHEAT")
        for item in body["recommendations"]:
            assert item["rotation"] is not None, f"{item['name']} has no rotation note"
            assert item["rotation"]["code"].startswith("rotation_")

    def test_the_note_appears_even_when_it_lost_the_reason_slots(self, client):
        """The exact gap this closes."""
        body = self._post(client, "WHEAT")
        for item in body["recommendations"]:
            in_reasons = any(r["factor"] == "rotation" for r in item["reasons"])
            if not in_reasons:
                assert item["rotation"] is not None
                return
        pytest.skip("rotation won a reason slot on every crop here")

    def test_no_previous_crop_means_no_note_rather_than_a_fake_one(self, client):
        body = self._post(client)
        assert all(item["rotation"] is None for item in body["recommendations"])

    def test_repeating_a_crop_is_the_lowest_rotation_score_on_the_page(self, client):
        body = self._post(client, "WHEAT")
        scores = {
            item["crop_code"]: item["rotation"]["score"]
            for item in body["recommendations"]
            if item["rotation"]
        }
        if "WHEAT" not in scores:
            pytest.skip("wheat dropped out of the top five entirely")
        assert scores["WHEAT"] == min(scores.values())


class TestBothOrderingsAreOffered:
    """Fit and return are different questions; the app must answer both.

    A farmer seeing chickpea at rank 1 and wheat earning 67% more concluded
    the ranking was broken. It was not — it was answering "what suits this
    field", where money is 9% of the score. Showing only that ordering made a
    reasonable person distrust a correct answer.
    """

    def _post(self, client, previous="WHEAT"):
        return client.post(
            "/api/v1/recommendations",
            json={
                "location": {
                    "type": "admin",
                    "state_code": "UP",
                    "district_code": "UP-LKO",
                },
                "season": "rabi",
                "area_ha": 2.5,
                "irrigation": "canal",
                "previous_crop": previous,
            },
        ).json()

    def test_every_priced_crop_gets_a_return_rank(self, client):
        for item in self._post(client)["recommendations"]:
            if item["economics"]["net_margin"] is not None:
                assert item["rank_by_return"] is not None

    def test_an_unpriced_crop_is_not_given_a_position(self, client):
        """Guessing a rank for a crop whose earnings we declined to state
        would invent the very number we refused to invent."""
        for item in self._post(client)["recommendations"]:
            if item["economics"]["net_margin"] is None:
                assert item["rank_by_return"] is None

    def test_the_return_ordering_actually_follows_the_money(self, client):
        priced = [
            item
            for item in self._post(client)["recommendations"]
            if item["rank_by_return"] is not None
        ]
        by_rank = sorted(priced, key=lambda item: item["rank_by_return"])
        margins = [item["economics"]["net_margin"] for item in by_rank]
        assert margins == sorted(margins, reverse=True)

    def test_the_two_orderings_are_allowed_to_disagree(self, client):
        """The whole point. If they could not differ the panel would be noise."""
        items = self._post(client)["recommendations"]
        by_fit = [i["crop_code"] for i in sorted(items, key=lambda x: x["rank"])]
        by_money = [
            i["crop_code"]
            for i in sorted(
                (i for i in items if i["rank_by_return"]),
                key=lambda x: x["rank_by_return"],
            )
        ]
        assert by_fit != by_money, "orderings identical here; try another field"

    def test_return_ranks_are_a_dense_sequence(self, client):
        """1, 2, 3 with no gaps, or the list looks like it lost a row."""
        ranks = sorted(
            item["rank_by_return"]
            for item in self._post(client)["recommendations"]
            if item["rank_by_return"] is not None
        )
        assert ranks == list(range(1, len(ranks) + 1))
