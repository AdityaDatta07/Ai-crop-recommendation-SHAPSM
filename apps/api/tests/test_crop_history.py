"""Cropping intensity read from NDVI, and the ways it lied before.

Two real defects, both found by running the thing rather than reading it:

  1. Counting runs above a greenness threshold merged paddy-then-wheat into a
     single eight-month cycle. NDVI never returns to bare soil between them.

  2. The same method counted the tail of a crop sown before the record began
     as a whole cycle, turning a rabi-only plot into a double-cropped one.

Both are regression-tested below with the exact series that exposed them.

The third property worth pinning is directional: cloud can only ever hide a
crop, never invent one, so a poor-coverage reading must understate intensity
and say so — never quietly overstate it.
"""

from __future__ import annotations

import pytest

from services.ml.crop_history import analyse


def series(values: list[float | None], start_year: int = 2024):
    """Monthly points from January of `start_year`."""
    return [
        (f"{start_year + i // 12}-{i % 12 + 1:02d}-15", value)
        for i, value in enumerate(values)
    ]


#: Kharif paddy into rabi wheat. NDVI stays above bare soil right through.
DOUBLE = [0.55, 0.50, 0.30, 0.15, 0.12, 0.35, 0.62, 0.75, 0.70, 0.45, 0.40, 0.58] * 2

#: Rabi only. Bare through the monsoon.
RABI_ONLY = [0.60, 0.55, 0.35, 0.15, 0.12, 0.14, 0.16, 0.18, 0.15, 0.20, 0.38, 0.58] * 2

#: The same rabi-only field, monsoon months lost to cloud.
RABI_CLOUDED = [0.55, 0.50, 0.30, 0.15, 0.12, None, None, None, None, None, 0.40, 0.58] * 2

#: Rainfed kharif, nothing after.
KHARIF_ONLY = [0.16, 0.14, 0.13, 0.12, 0.15, 0.42, 0.68, 0.74, 0.60, 0.30, 0.18, 0.16] * 2

#: Three cycles including a short summer crop.
TRIPLE = [0.62, 0.30, 0.55, 0.68, 0.25, 0.40, 0.70, 0.72, 0.35, 0.20, 0.45, 0.66] * 2

#: Nothing grown. Weeds after rain, no canopy.
FALLOW = [0.18, 0.16, 0.15, 0.14, 0.12, 0.20, 0.24, 0.22, 0.19, 0.17, 0.16, 0.18] * 2


class TestIntensity:
    @pytest.mark.parametrize(
        "name,values,expected",
        [
            ("double", DOUBLE, "double"),
            ("rabi only", RABI_ONLY, "single"),
            ("kharif only", KHARIF_ONLY, "single"),
            ("triple", TRIPLE, "triple"),
            ("fallow", FALLOW, "fallow"),
        ],
    )
    def test_intensity_is_read_correctly(self, name, values, expected):
        assert analyse(series(values)).intensity == expected

    def test_consecutive_crops_are_not_merged(self):
        """Regression: paddy into wheat counted as one crop.

        NDVI dips as the paddy is cut and the wheat emerges, but never to bare
        soil. A threshold-crossing method sees one long run; there are two
        crops, in two different seasons.
        """
        result = analyse(series(DOUBLE))
        assert set(result.seasons_used) == {"kharif", "rabi"}
        assert result.intensity == "double"

    def test_a_truncated_opening_crop_is_not_counted_whole(self):
        """Regression: a rabi-only plot reported as double-cropped.

        The record opens in January, mid-way through a crop sown the previous
        November. Counting that tail as a full cycle inflated the rate.
        """
        result = analyse(series(RABI_ONLY))
        assert result.intensity == "single"
        assert set(result.seasons_used) == {"rabi"}


class TestSeasonTiming:
    def test_peaks_are_dated_to_the_right_season(self):
        result = analyse(series(KHARIF_ONLY))
        assert all(cycle.season == "kharif" for cycle in result.cycles)

    def test_a_cycle_reports_its_span_and_peak(self):
        cycle = analyse(series(KHARIF_ONLY)).cycles[0]
        assert cycle.peak_month.startswith("202")
        assert cycle.peak_ndvi >= 0.4
        assert cycle.months >= 2


class TestCloudBiasIsDeclared:
    """Optical imagery can hide a crop. It cannot invent one."""

    def test_a_monsoon_gap_lowers_confidence(self):
        clear = analyse(series(RABI_ONLY))
        clouded = analyse(series(RABI_CLOUDED))
        assert clouded.confidence != "high"
        assert clear.confidence == "high"

    def test_a_monsoon_gap_is_named(self):
        result = analyse(series(RABI_CLOUDED))
        assert "kharif_cloud_gap" in result.caveat_codes

    def test_the_direction_of_the_error_is_stated(self):
        """Not "this may be inaccurate" — which way it is wrong."""
        result = analyse(series(RABI_CLOUDED))
        assert "may_understate_intensity" in result.caveat_codes

    def test_coverage_is_reported_per_season(self):
        result = analyse(series(RABI_CLOUDED))
        assert result.season_coverage["kharif"] == 0.0
        assert result.season_coverage["rabi"] > 0.5


class TestUnknownIsNeverConfident:
    """Regression: "Not clear" printed beside a high-confidence badge.

    A flat, low NDVI series with GOOD coverage produced intensity=unknown and
    confidence=high, and the UI rendered "Too few clear satellite passes"
    directly above "20 of 24 months had a clear satellite view". Two things
    were wrong: the confidence, and the diagnosis.
    """

    #: Flat and low for two years, four months lost to cloud. The dead zone:
    #: too green to be bare, never green enough to be a crop.
    FLAT = [0.30, 0.29, 0.31, 0.28, 0.30, 0.32, 0.33, 0.31, 0.29, 0.30, 0.28, 0.31] * 2

    def _flat_with_gaps(self):
        values = list(self.FLAT)
        for i in (3, 9, 15, 20):
            values[i] = None
        return series(values)

    def test_good_coverage_and_no_crop_is_not_unknown(self):
        """We saw it clearly. Nothing grew. That is a finding, not a blind spot."""
        result = analyse(self._flat_with_gaps())
        assert result.intensity == "uncropped"
        assert result.observed_months == 20

    def test_unknown_is_always_low_confidence(self):
        """If we cannot say what the pattern is, we are not confident in it."""
        blind = [0.6, None, None, None, 0.5, None, None, None, None, None, None, None] * 2
        result = analyse(series(blind))
        assert result.intensity == "unknown"
        assert result.confidence == "low"

    def test_uncropped_is_distinguished_from_fallow(self):
        """Bare earth and permanent light cover are different situations."""
        bare = [0.15, 0.14, 0.16, 0.13, 0.12, 0.18, 0.20, 0.19, 0.17, 0.16, 0.15, 0.14] * 2
        assert analyse(series(bare)).intensity == "fallow"
        assert analyse(self._flat_with_gaps()).intensity == "uncropped"


class TestRefusalToGuess:
    def test_too_few_observations_returns_unknown(self):
        sparse = [0.6, None, None, None, 0.5, None, None, None, None, None, None, None]
        result = analyse(series(sparse))
        assert result.intensity == "unknown"
        assert "too_few_observations" in result.caveat_codes

    def test_an_empty_series_does_not_crash(self):
        result = analyse([])
        assert result.intensity == "unknown"
        assert result.cycles == ()

    def test_gaps_are_not_interpolated_across(self):
        """A cloud gap must break the series, not be bridged.

        Bridging would invent a canopy nobody observed — the single thing this
        module exists to avoid.
        """
        bridged = [0.15, 0.15, None, None, None, None, 0.15, 0.15] * 3
        assert analyse(series(bridged)).cycles == ()

    def test_a_perennial_canopy_is_not_a_crop_cycle(self):
        """An orchard is green all year. That is not sowing and harvesting."""
        orchard = [0.72, 0.74, 0.73, 0.75, 0.74, 0.72, 0.76, 0.75, 0.73, 0.74, 0.72, 0.75] * 2
        assert analyse(series(orchard)).cycles == ()


class TestNothingIsFabricated:
    def test_fallow_months_only_count_months_actually_seen(self):
        """A month hidden by cloud is not a bare month."""
        result = analyse(series(RABI_CLOUDED))
        assert result.fallow_months <= result.observed_months

    def test_observed_never_exceeds_total(self):
        result = analyse(series(RABI_CLOUDED))
        assert result.observed_months <= result.total_months
        assert result.total_months == 24
