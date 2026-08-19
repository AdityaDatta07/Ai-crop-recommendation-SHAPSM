"""The risk and diversification service.

The claim this panel makes to a farmer is: "split your field and you are less
exposed, and here is what that costs you." Three ways that claim can be false,
and a test for each:

  - the partner is not actually independent (it fails for the same reasons)
  - the partner is worse than what it hedges (no price floor, poor fit)
  - the cost cannot be stated, so the trade-off is unknowable

The last two were real defects found by rendering the first version: it offered
onion beside pigeon pea, which swapped a guaranteed support price for none on
40% of the field and produced a null combined margin.
"""

from __future__ import annotations

import pytest

from apps.api.services import diversification as div
from services.ml.types import CropSpec, DateWindow, Risk


def crop(
    code: str,
    *,
    risks: tuple[Risk, ...] = (),
    price: int | None = 5000,
    irrigation_need: str = "medium",
) -> CropSpec:
    return CropSpec(
        crop_code=code,
        name=code.title(),
        name_hi=None,
        category="test",
        seasons=("kharif",),
        ph_optimal=(6.0, 7.5),
        ph_absolute=(5.0, 8.5),
        temp_optimal_c=(20.0, 30.0),
        temp_absolute_c=(10.0, 40.0),
        rainfall_mm=(400.0, 800.0),
        irrigation_need=irrigation_need,
        texture_preferred=("loam",),
        nitrogen_demand="medium",
        legume=False,
        duration_days=120,
        sowing_window=DateWindow(start="06-15", end="07-15"),
        varieties=(),
        risks=risks,
        price_per_quintal=price,
        cost_a2fl_per_quintal=None if price is None else price // 2,
        yield_kg_per_ha=2000.0,
    )


PEST = Risk(type="pest", name="Pod borer", severity="high")
DISEASE = Risk(type="disease", name="Wilt", severity="medium")
DROUGHT = Risk(type="weather", name="Drought", severity="high")


class TestExposure:
    def test_msp_crop_is_price_protected(self):
        exposure = div.assess(crop("A", price=5000), irrigation="canal", has_market_price=True)
        assert exposure.price == "low"

    def test_no_msp_and_no_market_price_is_fully_exposed(self):
        exposure = div.assess(crop("A", price=None), irrigation="canal", has_market_price=False)
        assert exposure.price == "high"
        assert "no_price_floor" in exposure.drivers

    def test_thirsty_crop_on_rainfed_land_is_water_exposed(self):
        exposure = div.assess(
            crop("A", irrigation_need="high"), irrigation="rainfed", has_market_price=True
        )
        assert exposure.water == "high"

    def test_irrigation_removes_water_exposure(self):
        exposure = div.assess(
            crop("A", irrigation_need="high"), irrigation="tubewell", has_market_price=True
        )
        assert exposure.water == "low"

    def test_severe_risks_are_named_not_just_counted(self):
        """A farmer can act on "pod borer". They cannot act on "high"."""
        exposure = div.assess(
            crop("A", risks=(PEST, DISEASE)), irrigation="canal", has_market_price=True
        )
        assert "Pod borer" in exposure.severe_risks
        assert "Wilt" not in exposure.severe_risks  # medium, not high


class TestOverlap:
    def test_identical_crops_overlap_completely(self):
        a = div.assess(crop("A", risks=(DROUGHT,), price=None), irrigation="rainfed",
                       has_market_price=False)
        b = div.assess(crop("B", risks=(DROUGHT,), price=None), irrigation="rainfed",
                       has_market_price=False)
        assert div.overlap(a, b) == pytest.approx(1.0)

    def test_unrelated_crops_do_not_overlap(self):
        a = div.assess(crop("A", risks=(PEST,)), irrigation="canal", has_market_price=True)
        b = div.assess(crop("B", risks=(DISEASE,)), irrigation="canal", has_market_price=True)
        assert div.overlap(a, b) == pytest.approx(0.0)

    def test_shared_weather_risk_counts_more_than_shared_pest(self):
        """A pest of one crop rarely touches another. A drought touches both."""
        base = div.assess(crop("A", risks=(DROUGHT, PEST)), irrigation="canal",
                          has_market_price=True)
        shares_weather = div.assess(crop("B", risks=(DROUGHT, DISEASE)), irrigation="canal",
                                    has_market_price=True)
        shares_pest = div.assess(crop("C", risks=(PEST, DISEASE)), irrigation="canal",
                                 has_market_price=True)

        assert div.overlap(base, shares_weather) > div.overlap(base, shares_pest)


class TestPlan:
    def _ranked(self, specs):
        """(crop, score, margin_per_ha) in rank order."""
        return [(spec, score, margin) for spec, score, margin in specs]

    def test_small_plot_is_not_split(self):
        result = div.build(
            self._ranked([(crop("A", risks=(PEST,)), 0.9, 30000),
                          (crop("B", risks=(DISEASE,)), 0.85, 28000)]),
            area_ha=0.2,
            irrigation="canal",
            priced_codes={"A", "B"},
        )
        assert result.plan == ()
        assert result.verdict_code == "plot_too_small"

    def test_unpriceable_partner_is_rejected(self):
        """The panel's claim is "this costs you X". No price, no X, no claim."""
        result = div.build(
            self._ranked([(crop("A", risks=(PEST,)), 0.9, 30000),
                          (crop("B", risks=(DISEASE,), price=None), 0.88, None)]),
            area_ha=2.0,
            irrigation="canal",
            priced_codes={"A"},
        )
        assert result.plan == ()
        assert result.verdict_code == "no_suitable_partner"

    def test_partner_may_not_be_more_price_exposed(self):
        """Trading a support price for none is not risk reduction."""
        protected = crop("A", risks=(PEST,), price=5000)
        exposed = crop("B", risks=(DISEASE,), price=None)

        result = div.build(
            self._ranked([(protected, 0.9, 30000), (exposed, 0.88, 32000)]),
            area_ha=2.0,
            irrigation="canal",
            priced_codes={"A", "B"},  # B has a market price but still no floor
        )
        assert result.plan == ()

    def test_poorly_suited_partner_is_rejected(self):
        result = div.build(
            self._ranked([(crop("A", risks=(PEST,)), 0.9, 30000),
                          (crop("B", risks=(DISEASE,)), 0.30, 28000)]),
            area_ha=2.0,
            irrigation="canal",
            priced_codes={"A", "B"},
        )
        assert result.plan == ()
        assert result.verdict_code == "no_suitable_partner"

    def test_says_so_when_every_candidate_shares_the_risk(self):
        """The honest non-answer, and a useful one."""
        result = div.build(
            self._ranked([
                (crop("A", risks=(DROUGHT,), irrigation_need="high"), 0.9, 30000),
                (crop("B", risks=(DROUGHT,), irrigation_need="high"), 0.88, 28000),
            ]),
            area_ha=2.0,
            irrigation="rainfed",
            priced_codes={"A", "B"},
        )
        assert result.plan == ()
        assert result.verdict_code == "everything_shares_the_risk"

    def test_independent_partner_produces_a_split(self):
        result = div.build(
            self._ranked([(crop("A", risks=(PEST,)), 0.9, 30000),
                          (crop("B", risks=(DISEASE,)), 0.85, 20000)]),
            area_ha=2.0,
            irrigation="canal",
            priced_codes={"A", "B"},
        )
        assert result.verdict_code == "split_reduces_risk"
        assert len(result.plan) == 2

    def test_shares_sum_to_the_whole_field(self):
        result = div.build(
            self._ranked([(crop("A", risks=(PEST,)), 0.9, 30000),
                          (crop("B", risks=(DISEASE,)), 0.85, 20000)]),
            area_ha=2.0,
            irrigation="canal",
            priced_codes={"A", "B"},
        )
        assert sum(a.share for a in result.plan) == pytest.approx(1.0)
        assert sum(a.area_ha for a in result.plan) == pytest.approx(2.0, abs=0.01)

    def test_the_best_crop_keeps_the_majority(self):
        """The split hedges the top crop; it does not replace it."""
        result = div.build(
            self._ranked([(crop("A", risks=(PEST,)), 0.9, 30000),
                          (crop("B", risks=(DISEASE,)), 0.89, 20000)]),
            area_ha=2.0,
            irrigation="canal",
            priced_codes={"A", "B"},
        )
        assert result.plan[0].share > result.plan[1].share
        assert result.plan[1].share <= div.MAX_PARTNER_SHARE

    def test_the_cost_of_the_split_is_reported(self):
        """Diversifying usually earns less. Hiding that would be the lie."""
        result = div.build(
            self._ranked([(crop("A", risks=(PEST,)), 0.9, 30000),
                          (crop("B", risks=(DISEASE,)), 0.85, 10000)]),
            area_ha=2.0,
            irrigation="canal",
            priced_codes={"A", "B"},
        )
        assert result.single_crop_margin == 60000  # all-in on the better earner
        assert result.combined_margin is not None
        assert result.combined_margin < result.single_crop_margin
        assert result.margin_given_up == result.single_crop_margin - result.combined_margin

    def test_combined_margin_is_the_sum_of_the_parts(self):
        """The one arithmetic claim this service makes, checked."""
        result = div.build(
            self._ranked([(crop("A", risks=(PEST,)), 0.9, 30000),
                          (crop("B", risks=(DISEASE,)), 0.85, 20000)]),
            area_ha=2.0,
            irrigation="canal",
            priced_codes={"A", "B"},
        )
        parts = sum(a.net_margin for a in result.plan)
        assert result.combined_margin == parts

    def test_baseline_is_the_best_earner_not_the_top_ranked_crop(self):
        """The regression this exists to prevent.

        Ranking is by agronomic fit, so rank 1 can earn far less per hectare
        than rank 2. Comparing the split against rank 1 alone produced the
        sentence "this split earns more than a single crop" on a screen where
        planting all of rank 2 would have beaten the split by more still.

        A farmer reading that would have diversified on the strength of a
        false claim about their own money.
        """
        fits_best_earns_less = crop("MAIZE", risks=(PEST,))
        fits_worse_earns_more = crop("WHEAT", risks=(DISEASE,))

        result = div.build(
            [(fits_best_earns_less, 0.92, 18130), (fits_worse_earns_more, 0.90, 55288)],
            area_ha=2.5,
            irrigation="canal",
            priced_codes={"MAIZE", "WHEAT"},
        )

        # The baseline must be all-in on wheat, not all-in on maize.
        assert result.single_crop_code == "WHEAT"
        assert result.single_crop_margin == round(55288 * 2.5)

        # And so the split must be reported as costing money, not earning it.
        assert result.margin_given_up is not None
        assert result.margin_given_up > 0
        assert result.combined_margin < result.single_crop_margin

    def test_baseline_is_never_beaten_by_any_single_crop_in_the_list(self):
        """Stated as the invariant rather than one example of it."""
        specs = [
            (crop("A", risks=(PEST,)), 0.90, 10000),
            (crop("B", risks=(DISEASE,)), 0.88, 45000),
            (crop("C", risks=(DROUGHT,)), 0.80, 22000),
        ]
        result = div.build(specs, area_ha=3.0, irrigation="canal",
                           priced_codes={"A", "B", "C"})

        best_possible = max(round(margin * 3.0) for _, _, margin in specs)
        assert result.single_crop_margin == best_possible

    def test_an_evenly_matched_split_costs_nothing(self):
        """The UI shows "about level" here rather than a cost of zero."""
        # Both crops earn the same per hectare, so any split ties the best
        # single crop exactly — the only way a split can fail to cost money
        # once the baseline is the best earner.
        result = div.build(
            self._ranked([(crop("A", risks=(PEST,)), 0.9, 30000),
                          (crop("B", risks=(DISEASE,)), 0.88, 30000)]),
            area_ha=2.0,
            irrigation="canal",
            priced_codes={"A", "B"},
        )
        assert result.margin_given_up == 0

    def test_no_crops_is_handled(self):
        result = div.build([], area_ha=2.0, irrigation="canal", priced_codes=set())
        assert result.verdict_code == "no_crops"
        assert result.exposures == ()
