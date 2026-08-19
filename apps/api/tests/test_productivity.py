"""Plot vigour against the surrounding farmland.

Two failure modes drive these tests.

THE COMPARISON MUST BE FAIR
---------------------------
The plot figure and the neighbourhood figure have to come from the same
imagery and the same compositing. The plot's amplitude was available for free
from the monthly NDVI series already fetched for the history chart — using it
would have compared a monthly MEAN against per-scene maxima, and monthly means
smooth peaks away. Every field would have looked less vigorous than its
surroundings for purely arithmetic reasons, and the bug would have been
invisible because the answer is plausible.

THE NEIGHBOURHOOD MUST BE CROPLAND
----------------------------------
An unmasked 10 km circle is mostly roads, roofs and water. Those sit near zero
amplitude, drag the median down, and flatter every real field into the top
decile. The mask is what makes the comparison mean anything.
"""

from __future__ import annotations

import pytest

from services.ml.productivity import analyse, amplitude_of

#: Ordinary irrigated cropland: a wide spread with a middle around 0.42.
NEIGHBOURHOOD = {10: 0.18, 25: 0.28, 50: 0.42, 75: 0.55, 90: 0.66}


def placed(amplitude: float, **kwargs):
    return analyse(
        amplitude,
        NEIGHBOURHOOD,
        neighbourhood_km=10,
        sample_pixels=kwargs.pop("sample_pixels", 5000),
        **kwargs,
    )


class TestPlacement:
    @pytest.mark.parametrize(
        "amplitude,expected",
        [
            (0.72, "well_above"),
            (0.58, "well_above"),
            (0.44, "typical"),
            (0.40, "typical"),
            (0.30, "below"),
            (0.12, "well_below"),
        ],
    )
    def test_a_plot_lands_in_the_right_band(self, amplitude, expected):
        assert placed(amplitude).band == expected

    def test_the_percentile_rises_with_the_amplitude(self):
        values = [placed(a).percentile for a in (0.15, 0.30, 0.45, 0.60, 0.70)]
        assert values == sorted(values)

    def test_a_plot_at_the_median_reads_as_typical(self):
        result = placed(NEIGHBOURHOOD[50])
        assert result.percentile == 50
        assert result.band == "typical"

    def test_near_the_middle_is_typical_not_above_average(self):
        """53rd percentile is not a finding. Calling it one implies a precision
        five sampled breakpoints cannot support."""
        assert placed(0.44).band == "typical"

    def test_values_beyond_the_range_are_clamped_not_extrapolated(self):
        """We know the plot beats the 90th. Claiming the 99th would be
        inventing precision from a distribution we sampled five points of."""
        assert placed(0.95).percentile == 90
        assert placed(0.01).percentile == 10


class TestRefusalToCompare:
    def test_too_little_cropland_nearby_is_not_a_ranking(self):
        result = placed(0.5, sample_pixels=40)
        assert result.band == "unknown"
        assert "neighbourhood_too_small" in result.caveat_codes

    def test_no_plot_reading_is_not_a_zero(self):
        result = analyse(None, NEIGHBOURHOOD, neighbourhood_km=10, sample_pixels=5000)
        assert result.band == "unknown"
        assert result.percentile is None

    def test_no_distribution_means_no_comparison(self):
        result = analyse(0.5, {}, neighbourhood_km=10, sample_pixels=5000)
        assert result.band == "unknown"
        assert "no_comparison_available" in result.caveat_codes

    def test_a_single_breakpoint_is_not_a_distribution(self):
        result = analyse(0.5, {50: 0.42}, neighbourhood_km=10, sample_pixels=5000)
        assert result.band == "unknown"


class TestTheCaveatsAreAlwaysAttached:
    def test_the_yield_caveat_is_never_omitted(self):
        """The single most likely misreading: biomass taken for grain."""
        assert "not_a_yield_measure" in placed(0.5).caveat_codes
        assert "not_a_yield_measure" in placed(0.1).caveat_codes

    def test_a_cloudy_season_is_flagged_as_understating(self):
        """Cloud lowers the measured peak, which lowers the amplitude, which
        pushes the plot down for a reason unrelated to the field."""
        result = placed(0.5, season_coverage=0.3)
        assert "cloud_may_understate" in result.caveat_codes

    def test_a_clear_season_carries_no_cloud_caveat(self):
        assert "cloud_may_understate" not in placed(0.5, season_coverage=1.0).caveat_codes


class TestAmplitudeHelper:
    def test_amplitude_is_peak_minus_trough(self):
        assert amplitude_of([0.15, 0.40, 0.75, 0.30]) == pytest.approx(0.60)

    def test_gaps_are_skipped_not_treated_as_zero(self):
        assert amplitude_of([0.15, None, 0.75, None]) == pytest.approx(0.60)

    def test_a_series_with_one_reading_has_no_amplitude(self):
        assert amplitude_of([0.5, None, None]) is None
        assert amplitude_of([]) is None


class TestTheEarthEngineQueryIsFair:
    """Read from the source, because this cannot be executed without credentials.

    Both properties here are invisible when wrong: the answer still looks
    plausible, it is just systematically biased.
    """

    def _source(self) -> str:
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        text = (root / "services" / "geo" / "earthengine.py").read_text(encoding="utf-8")
        start = text.index("def _productivity")
        return text[start : text.index("def _index_bands")]

    def test_the_neighbourhood_is_masked_to_cropland(self):
        source = self._source()
        assert "CROPLAND_PEAK_NDVI" in source, (
            "An unmasked circle is mostly roads and roofs. They sit near zero "
            "amplitude, drag the median down, and flatter every field."
        )
        assert "updateMask" in source

    def test_both_sides_are_measured_from_the_same_image(self):
        """The plot and the neighbourhood must share one amplitude image.

        Taking the plot's figure from the monthly history instead would compare
        a smoothed mean against per-scene maxima.
        """
        source = self._source()
        assert source.count("_seasonal_amplitude(") == 1
        assert "amplitude.reduceRegion" in source

    def test_amplitude_is_peak_minus_trough_not_peak_alone(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        text = (root / "services" / "geo" / "earthengine.py").read_text(encoding="utf-8")
        block = text[text.index("def _seasonal_amplitude") : text.index("def _productivity")]
        assert "peak.subtract(trough)" in block, (
            "Peak NDVI alone ranks orchards and scrub above real crops."
        )


class TestSeasonWindowDates:
    def test_rabi_steps_back_across_the_new_year(self):
        from datetime import date

        from services.geo.earthengine import _season_dates

        start, end = _season_dates(date(2026, 8, 19), 10, 2)
        assert start.month == 10
        assert end.month == 2
        assert end > start, "a window that ends before it starts samples nothing"

    def test_a_window_never_starts_in_the_future(self):
        from datetime import date

        from services.geo.earthengine import _season_dates

        start, _ = _season_dates(date(2026, 3, 1), 6, 9)
        assert start <= date(2026, 3, 1)


class TestTheQueryActuallyRuns:
    """Execute _productivity against a stand-in Earth Engine.

    Static reading catches a missing mask; it does not catch a typo'd result
    key. Earth Engine names a combined percentile+count reduction
    `<band>_p10 ... <band>_count`, and getting that wrong returns None for
    everything — which the analysis would faithfully report as "no comparison
    available" rather than as the bug it is.
    """

    def _fake_ee(self, payload):
        class Node:
            def __init__(self, outer):
                self._outer = outer

            def __getattr__(self, name):
                def call(*args, **kwargs):
                    if name == "map":
                        pass
                    return self
                return call

            def getInfo(self):
                return payload

        class Reducer:
            def __init__(self, outer):
                self._outer = outer

            def percentile(self, values):
                self._outer.percentiles_asked = list(values)
                return Node(self._outer)

            def count(self):
                return Node(self._outer)

            def mean(self):
                return Node(self._outer)

        class Geometry:
            def __init__(self, outer):
                self._outer = outer

            def Point(self, coords):
                return Node(self._outer)

        class FakeEE:
            def __init__(self):
                self.percentiles_asked = None
                self.Reducer = Reducer(self)
                self.Geometry = Geometry(self)
                self.Filter = Node(self)

            def ImageCollection(self, name):
                return Node(self)

        return FakeEE()

    def test_it_reads_the_keys_earth_engine_actually_returns(self):
        from datetime import date

        from services.geo.earthengine import _productivity

        payload = {
            "amplitude_p10": 0.18,
            "amplitude_p25": 0.28,
            "amplitude_p50": 0.42,
            "amplitude_p75": 0.55,
            "amplitude_p90": 0.66,
            "amplitude_count": 8123,
            "amplitude": 0.61,
        }
        fake = self._fake_ee(payload)
        result = _productivity(
            fake, object(), (80.9, 26.8), date(2025, 11, 1), date(2026, 2, 28)
        )

        assert result["plot_amplitude"] == 0.61
        assert result["percentiles"][50] == 0.42
        assert result["sample_pixels"] == 8123
        assert result["neighbourhood_km"] == 10.0

    def test_it_asks_for_the_percentiles_the_analysis_expects(self):
        from datetime import date

        from services.geo.earthengine import _productivity
        from services.ml.productivity import PERCENTILES

        fake = self._fake_ee({})
        _productivity(fake, object(), (80.9, 26.8), date(2025, 11, 1), date(2026, 2, 28))
        assert tuple(fake.percentiles_asked) == PERCENTILES

    def test_the_whole_path_produces_a_usable_reading(self):
        """End to end: raw Earth Engine shape in, farmer-facing band out."""
        from datetime import date

        from services.geo.earthengine import _productivity
        from services.ml.productivity import analyse

        fake = self._fake_ee(
            {
                "amplitude_p10": 0.18,
                "amplitude_p25": 0.28,
                "amplitude_p50": 0.42,
                "amplitude_p75": 0.55,
                "amplitude_p90": 0.66,
                "amplitude_count": 8123,
                "amplitude": 0.61,
            }
        )
        raw = _productivity(
            fake, object(), (80.9, 26.8), date(2025, 11, 1), date(2026, 2, 28)
        )
        reading = analyse(
            raw["plot_amplitude"],
            raw["percentiles"],
            neighbourhood_km=raw["neighbourhood_km"],
            sample_pixels=raw["sample_pixels"],
        )
        assert reading.band == "well_above"
        assert reading.percentile is not None


class TestItDoesNotJudgeAPlotWithNoCrop:
    """Two panels on one page must not contradict each other.

    The crop-history panel had already concluded this plot grew nothing in two
    years. The productivity panel then ranked it in the 17th percentile of the
    surrounding farmland — which reads as "you farm badly" when the finding is
    "there is no crop here". Both were computed from the same imagery of the
    same place.
    """

    def test_no_crop_means_no_percentile(self):
        result = analyse(
            0.12,
            NEIGHBOURHOOD,
            neighbourhood_km=10,
            sample_pixels=37469,
            crop_detected=False,
        )
        assert result.percentile is None
        assert result.band == "unknown"
        assert "no_crop_to_compare" in result.caveat_codes

    def test_the_amplitude_is_still_reported(self):
        """The measurement is real and worth showing; only the ranking is withheld."""
        result = analyse(
            0.12, NEIGHBOURHOOD, neighbourhood_km=10, sample_pixels=5000, crop_detected=False
        )
        assert result.plot_amplitude == pytest.approx(0.12)

    def test_a_cropped_plot_is_still_ranked(self):
        result = analyse(
            0.12, NEIGHBOURHOOD, neighbourhood_km=10, sample_pixels=5000, crop_detected=True
        )
        assert result.band == "well_below"
