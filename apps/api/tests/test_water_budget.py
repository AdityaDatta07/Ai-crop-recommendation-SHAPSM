"""The water budget, and the two ways it could quietly mislead.

  1. Effective rainfall computed on a seasonal total instead of month by month.
     The USDA SCS formula is defined per month; feeding it a whole monsoon
     writes most of the rain off as runoff and invents a deficit that is not
     there. 859 mm returns 210 mm the wrong way and 587 mm the right way.

  2. A missing rainfall reading returning a deficit of zero, which reads as
     "no irrigation needed" — the opposite of what is known.
"""

from __future__ import annotations

import pytest

from apps.api.services import water_budget as wb
from services.ml.types import CropSpec, DateWindow


def crop(code: str, *, rainfall: tuple[float, float], days: int = 130) -> CropSpec:
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
        rainfall_mm=rainfall,
        irrigation_need="medium",
        texture_preferred=("loam",),
        nitrogen_demand="medium",
        legume=False,
        duration_days=days,
        sowing_window=DateWindow(start="06-15", end="07-15"),
        varieties=(),
        risks=(),
        price_per_quintal=5000,
        cost_a2fl_per_quintal=2500,
        yield_kg_per_ha=2000.0,
    )


class TestEffectiveRainfall:
    def test_is_always_less_than_what_fell(self):
        for total in (50, 200, 500, 859, 1500):
            assert wb.effective_rainfall_mm(total, 130) < total

    def test_is_computed_month_by_month_not_on_the_season_total(self):
        """The regression guard for the arithmetic that matters most.

        Applied to 859 mm in one lump the SCS formula returns about 210 mm.
        Applied across the four-and-a-bit months the crop is in the ground it
        returns about 587 mm. The difference is a fabricated 375 mm deficit.
        """
        assert wb.effective_rainfall_mm(859, 130) == pytest.approx(587, abs=5)

    def test_zero_rainfall_is_zero(self):
        assert wb.effective_rainfall_mm(0, 130) == 0.0

    def test_a_longer_season_makes_more_of_the_same_rain_usable(self):
        """Same total, spread thinner, less runoff."""
        short = wb.effective_rainfall_mm(800, 90)
        long = wb.effective_rainfall_mm(800, 180)
        assert long > short


class TestBudget:
    def test_missing_rainfall_does_not_become_a_zero_deficit(self):
        """Unknown must not render as "no irrigation needed"."""
        budget = wb.build(
            crop("A", rainfall=(600, 900)),
            season_rainfall_mm=None,
            area_ha=2.0,
            irrigation="rainfed",
        )
        assert budget.status == "unknown"
        assert budget.deficit_mm is None
        assert budget.waterings is None

    def test_ample_rain_needs_no_irrigation(self):
        budget = wb.build(
            crop("A", rainfall=(300, 600)),
            season_rainfall_mm=900,
            area_ha=2.0,
            irrigation="rainfed",
        )
        assert budget.deficit_mm == 0
        assert budget.waterings == 0
        assert budget.status in ("rain_sufficient", "surplus")

    def test_shortfall_on_rainfed_land_cannot_be_met(self):
        """The distinction the risk panel depends on."""
        budget = wb.build(
            crop("A", rainfall=(900, 1200)),
            season_rainfall_mm=300,
            area_ha=2.0,
            irrigation="rainfed",
        )
        assert budget.status == "cannot_meet"
        assert budget.can_be_met is False

    def test_same_shortfall_with_a_tubewell_is_only_a_gap_to_close(self):
        budget = wb.build(
            crop("A", rainfall=(900, 1200)),
            season_rainfall_mm=300,
            area_ha=2.0,
            irrigation="tubewell",
        )
        assert budget.status == "needs_irrigation"
        assert budget.can_be_met is True
        assert budget.waterings and budget.waterings > 0

    def test_volume_is_the_gap_times_the_area(self):
        """1 mm over 1 ha is 10 m3. A unit conversion, so it must be exact."""
        budget = wb.build(
            crop("A", rainfall=(900, 1200)),
            season_rainfall_mm=300,
            area_ha=3.0,
            irrigation="tubewell",
        )
        assert budget.deficit_m3 == pytest.approx(budget.deficit_mm * 10 * 3.0, abs=1)

    def test_volume_scales_with_the_plot_but_the_gap_does_not(self):
        """mm is a depth, m3 is a quantity. Confusing them is how a plan for
        one hectare gets applied to ten."""
        small = wb.build(crop("A", rainfall=(900, 1200)), season_rainfall_mm=300,
                         area_ha=1.0, irrigation="tubewell")
        large = wb.build(crop("A", rainfall=(900, 1200)), season_rainfall_mm=300,
                         area_ha=10.0, irrigation="tubewell")

        assert small.deficit_mm == large.deficit_mm
        assert large.deficit_m3 == pytest.approx(small.deficit_m3 * 10, abs=1)

    def test_waterings_round_up(self):
        """Two-thirds of a watering is not a thing a farmer can do."""
        budget = wb.build(
            crop("A", rainfall=(500, 800)),
            season_rainfall_mm=400,
            area_ha=1.0,
            irrigation="canal",
        )
        assert budget.deficit_mm is not None and budget.waterings is not None
        assert budget.waterings >= budget.deficit_mm / wb.APPLICATION_DEPTH_MM

    def test_far_too_much_rain_is_flagged_as_drainage_not_bounty(self):
        budget = wb.build(
            crop("A", rainfall=(200, 300)),
            season_rainfall_mm=1400,
            area_ha=1.0,
            irrigation="canal",
        )
        assert budget.status == "surplus"
        assert budget.surplus_mm and budget.surplus_mm > 0


class TestWhichEndOfTheRange:
    """The gap closes to the crop's MINIMUM, and the panel has to say so.

    "Needs 400-650 mm, gap 325 mm, about 6 waterings" reads as though six
    waterings land the crop inside its band. They land it on 400 — the bottom
    edge. Reaching 650 takes ten. A farmer who under-waters while believing
    they followed the advice is the failure this guards against.
    """

    def test_waterings_target_the_minimum(self):
        budget = wb.build(
            crop("A", rainfall=(400, 650), days=135),
            season_rainfall_mm=77.0,
            area_ha=2.5,
            irrigation="canal",
        )
        reached = budget.effective_rainfall_mm + budget.waterings * wb.APPLICATION_DEPTH_MM
        assert reached >= budget.requirement_mm
        assert reached < budget.comfortable_mm, "should not already be comfortable"

    def test_the_comfortable_target_is_reported_too(self):
        budget = wb.build(
            crop("A", rainfall=(400, 650), days=135),
            season_rainfall_mm=77.0,
            area_ha=2.5,
            irrigation="canal",
        )
        assert budget.waterings_comfortable is not None
        assert budget.waterings_comfortable > budget.waterings

        reached = (
            budget.effective_rainfall_mm
            + budget.waterings_comfortable * wb.APPLICATION_DEPTH_MM
        )
        assert reached >= budget.comfortable_mm

    def test_both_targets_are_null_when_rainfall_is(self):
        budget = wb.build(
            crop("A", rainfall=(400, 650)),
            season_rainfall_mm=None,
            area_ha=2.5,
            irrigation="canal",
        )
        assert budget.waterings_comfortable is None
        assert budget.deficit_comfortable_mm is None


class TestAgreementWithTheRiskPanel:
    """Two panels describing the same field must not contradict each other."""

    def test_risk_water_level_follows_the_budget(self):
        from apps.api.services import diversification as div

        spec = crop("A", rainfall=(900, 1200))
        dry = wb.build(spec, season_rainfall_mm=200, area_ha=2.0, irrigation="rainfed")
        assert dry.status == "cannot_meet"

        exposure = div.assess(
            spec, irrigation="rainfed", has_market_price=True, water_status=dry.status
        )
        assert exposure.water == "high"

    def test_a_met_need_reads_as_low_exposure_even_on_rainfed_land(self):
        """The case the old category-based rule got wrong: plenty of rain, but
        the crop was badged medium purely for being rainfed."""
        from apps.api.services import diversification as div

        spec = crop("A", rainfall=(200, 400))
        wet = wb.build(spec, season_rainfall_mm=900, area_ha=2.0, irrigation="rainfed")
        assert wet.deficit_mm == 0

        exposure = div.assess(
            spec, irrigation="rainfed", has_market_price=True, water_status=wet.status
        )
        assert exposure.water == "low"


class TestSeasonWindow:
    """The rainfall a budget is built on must be the FARMER's season.

    Found by reading a screenshot: a rabi plan requested in August was costed
    against 859 mm, which is the monsoon. Lucknow receives roughly 60 mm
    between October and February. Every rabi rainfall score was inflated and
    the water budget told wheat growers they needed no irrigation, when rabi
    wheat in that district needs four to six.
    """

    def test_the_selected_season_beats_the_calendar(self):
        from datetime import date

        from services.geo.earthengine import _season_window

        august = date(2026, 8, 19)
        assert _season_window(august, "rabi") == (10, 2)
        assert _season_window(august, "kharif") == (6, 9)
        assert _season_window(august, "zaid") == (3, 5)

    def test_the_calendar_is_still_the_fallback(self):
        """The field-summary endpoint has no season to offer."""
        from datetime import date

        from services.geo.earthengine import _season_window

        assert _season_window(date(2026, 8, 19), None) == (6, 9)
        assert _season_window(date(2026, 12, 1), None) == (10, 2)

    def test_an_unknown_season_falls_back_rather_than_crashing(self):
        from datetime import date

        from services.geo.earthengine import _season_window

        assert _season_window(date(2026, 8, 19), "monsoon") == (6, 9)


class TestWeatherIsSeasonal:
    """Rainfall AND temperature must both be filtered to the crop season.

    Temperature was an annual mean. Lucknow averages ~25 C over the year, ~18 C
    across rabi. At 25 C maize (ideal 21-30) scored 0.98 and wheat (18-25)
    scored 0.85 on the joint-highest-weighted factor, so a summer crop outranked
    wheat for a winter field. Reading the source is the only way to catch this
    without live Earth Engine credentials, so that is what this does.
    """

    def _weather_source(self) -> str:
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        text = (root / "services" / "geo" / "earthengine.py").read_text(encoding="utf-8")
        start = text.index("def _sample_climate")
        return text[start : text.index("def _texture_from")]

    def test_temperature_is_filtered_by_month(self):
        block = self._weather_source()
        temp_call = block[block.index("ERA5_LAND_MONTHLY") :]
        temp_call = temp_call[: temp_call.index("getInfo")]
        assert ".filter(" in temp_call, (
            "ERA5-Land temperature is being averaged over the whole year. "
            "It must be filtered to the crop season, like rainfall is."
        )

    def test_both_variables_share_one_season_window(self):
        block = self._weather_source()
        # One call, whose result both variables read. Two calls could drift.
        assert block.count("_season_window(") == 1, (
            "Rainfall and temperature must derive their months from the same "
            "call, or they can silently describe different seasons."
        )
