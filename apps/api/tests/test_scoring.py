"""Scoring functions. Pure, so these need no fixtures and no I/O."""

from __future__ import annotations

import pytest

from services.ml import scoring


class TestTaper:
    def test_peaks_at_band_centre(self):
        assert scoring.taper(7.0, (6.0, 8.0), (5.0, 9.0)) == pytest.approx(1.0)

    def test_in_band_edges_score_the_floor(self):
        assert scoring.taper(6.0, (6.0, 8.0), (5.0, 9.0)) == pytest.approx(scoring.IN_BAND_FLOOR)
        assert scoring.taper(8.0, (6.0, 8.0), (5.0, 9.0)) == pytest.approx(scoring.IN_BAND_FLOOR)

    def test_is_continuous_across_the_band_edge(self):
        just_inside = scoring.taper(6.001, (6.0, 8.0), (5.0, 9.0))
        just_outside = scoring.taper(5.999, (6.0, 8.0), (5.0, 9.0))
        assert abs(just_inside - just_outside) < 0.01

    def test_zero_outside_absolute_limits(self):
        assert scoring.taper(4.9, (6.0, 8.0), (5.0, 9.0)) == 0.0
        assert scoring.taper(9.1, (6.0, 8.0), (5.0, 9.0)) == 0.0

    def test_discriminates_between_crops_sharing_a_value(self):
        """The defect this was written for: everything in band tied on 1.0."""
        centred = scoring.taper(7.2, (7.0, 7.4), (5.0, 9.0))
        off_centre = scoring.taper(7.2, (6.0, 7.5), (5.0, 8.5))
        assert centred > off_centre


class TestMissingDataSemantics:
    def test_missing_field_measurement_returns_none(self):
        """None means 'we don't know about this field' - weight gets dropped."""
        assert scoring.score_ph(None, (6.0, 7.5), (5.0, 8.5)) is None
        assert scoring.score_temperature(None, (18.0, 25.0), (8.0, 35.0)) is None
        assert scoring.score_texture(None, ("loam",)) is None
        assert scoring.score_rainfall(None, (400.0, 650.0), "canal") is None

    def test_missing_crop_price_scores_low_instead_of_none(self):
        """A fact about the crop, not a gap in our survey. It must cost points."""
        assert scoring.score_market(None, None) == scoring.UNPRICED_SCORE
        assert scoring.is_priced(None, None) is False

    def test_priced_crop_scores_on_margin(self):
        thin = scoring.score_market(1100, 1000)
        fat = scoring.score_market(2000, 1000)
        assert 0 < thin < fat
        assert scoring.is_priced(2000, 1000) is True

    def test_legume_scores_nitrogen_without_a_soil_reading(self):
        assert scoring.score_nitrogen(None, "low", legume=True) == 1.0
        assert scoring.score_nitrogen(None, "high", legume=False) is None


class TestRainfallAndIrrigation:
    def test_irrigation_closes_a_shortfall(self):
        rainfed = scoring.score_rainfall(200.0, (400.0, 650.0), "rainfed")
        drip = scoring.score_rainfall(200.0, (400.0, 650.0), "drip")
        assert drip > rainfed

    def test_surplus_rainfall_is_not_a_bonus(self):
        ideal = scoring.score_rainfall(500.0, (400.0, 650.0), "rainfed")
        flooded = scoring.score_rainfall(1400.0, (400.0, 650.0), "rainfed")
        assert ideal == pytest.approx(1.0)
        assert flooded < ideal

    def test_rainfed_land_is_ideal_for_a_low_water_crop(self):
        """Regression: this scored 0.0, penalising exactly the right choice.

        A drought-tolerant crop on rainfed land is the commonest good decision
        our users make. It must score full marks.
        """
        assert scoring.score_irrigation("rainfed", "low") == 1.0

    def test_rainfed_land_is_marked_down_but_not_vetoed_for_a_thirsty_crop(self):
        """Whether the water balances is the rainfall factor's call, not this one."""
        thirsty = scoring.score_irrigation("rainfed", "high")
        assert thirsty == pytest.approx(scoring.IRRIGATION_FLOOR)
        assert thirsty < scoring.score_irrigation("rainfed", "low")
        assert scoring.score_irrigation("drip", "high") == 1.0
        assert scoring.score_irrigation("canal", "medium") == 1.0
