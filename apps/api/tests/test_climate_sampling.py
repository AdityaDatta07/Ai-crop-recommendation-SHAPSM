"""Exercise the Earth Engine sampling code without Earth Engine.

WHY THIS EXISTS
---------------
The season fix threaded a `season` argument through get_conditions, the
provider and the mock, and stopped one layer short: `_sample_climate` used the
name without taking it as a parameter. That is a NameError on every single
call.

Nothing caught it. The unit tests all ran in mock mode, which never reaches
this function. The integration tests ran in mock mode too. And the function's
own `except Exception` swallowed the NameError and returned None, so the API
came back 200 with empty weather and the UI politely reported "no rainfall
reading for this field" — a bug wearing the costume of missing data.

The fix is to run the real function against a stand-in `ee` module. It does not
verify any climatology; it verifies that the code executes, that the season
reaches the filters, and that a mistake in our own code is not disguised as an
upstream outage.
"""

from __future__ import annotations

import pytest

from services.geo import earthengine as engine
from services.geo.types import ResolvedLocation


class FakeEE:
    """Chainable stand-in for the Earth Engine client.

    Every call returns something chainable; getInfo returns fixed numbers. The
    point is that the real code path runs end to end, not that the values mean
    anything.
    """

    def __init__(self) -> None:
        self.calendar_ranges: list[tuple[int, int]] = []
        self.or_filters = 0

    # -- chainable node -----------------------------------------------------
    class _Node:
        def __init__(self, outer: "FakeEE", payload: dict) -> None:
            self._outer = outer
            self._payload = payload

        def __getattr__(self, _name):
            def call(*_args, **_kwargs):
                return self
            return call

        def getInfo(self):
            return self._payload

    # -- the surface the module actually uses -------------------------------
    @property
    def Geometry(self):
        outer = self

        class _Geometry:
            @staticmethod
            def Point(_coords):
                return outer._Node(outer, {})

        return _Geometry

    @property
    def Reducer(self):
        outer = self

        class _Reducer:
            @staticmethod
            def mean():
                return outer._Node(outer, {})

        return _Reducer

    @property
    def Filter(self):
        outer = self

        class _Filter:
            @staticmethod
            def calendarRange(start, end, _unit):
                outer.calendar_ranges.append((start, end))
                return outer._Node(outer, {})

            @staticmethod
            def Or(*args):
                outer.or_filters += 1
                return outer._Node(outer, {})

        return _Filter

    def ImageCollection(self, _name):
        # Values keyed the way the real reduceRegion result is read.
        return self._Node(
            self,
            {"precipitation": 30_000.0, "temperature_2m": 291.15},  # ~18 C
        )


PLACE = ResolvedLocation(
    state_code="UP",
    district_code="UP-LKO",
    district_name="Lucknow",
    centroid=(80.95, 26.85),
    area_ha=1.0,
)


class TestSamplingRuns:
    """The regression that started all this: does the function even execute?"""

    @pytest.mark.parametrize("season", ["kharif", "rabi", "zaid", None])
    def test_sampling_does_not_raise_for_any_season(self, season):
        weather = engine._sample_climate(FakeEE(), PLACE, 6000.0, season)

        assert weather.season_rainfall_mm is not None, (
            "Seasonal rainfall came back empty. Before, this was a NameError "
            "being swallowed and shown to farmers as missing data."
        )
        assert weather.avg_temp_c is not None

    def test_the_requested_season_reaches_the_month_filters(self):
        fake = FakeEE()
        engine._sample_climate(fake, PLACE, 6000.0, "rabi")

        # Rabi is October-February, so it must be requested as two ranges that
        # straddle the new year, not one range from 10 to 2.
        assert (10, 12) in fake.calendar_ranges
        assert (1, 2) in fake.calendar_ranges
        assert fake.or_filters >= 1

    def test_kharif_is_a_single_unwrapped_range(self):
        fake = FakeEE()
        engine._sample_climate(fake, PLACE, 6000.0, "kharif")

        assert (6, 9) in fake.calendar_ranges

    def test_rainfall_and_temperature_use_the_same_months(self):
        """Both variables must describe the same season, or the page lies."""
        fake = FakeEE()
        engine._sample_climate(fake, PLACE, 6000.0, "rabi")

        # Two variables x two ranges each for a wrapping season.
        assert fake.calendar_ranges.count((10, 12)) == 2
        assert fake.calendar_ranges.count((1, 2)) == 2


class TestBugsAreNotDisguisedAsOutages:
    def test_a_programming_error_is_raised_not_swallowed(self):
        """The behaviour that let the original bug ship silently.

        A broken client must fail loudly. Only genuine upstream trouble is
        allowed to degrade into empty conditions.
        """

        class BrokenEE(FakeEE):
            def ImageCollection(self, _name):
                raise AttributeError("typo in a chained call")

        with pytest.raises(AttributeError):
            engine._sample_climate(BrokenEE(), PLACE, 6000.0, "rabi")

    def test_an_upstream_outage_still_degrades_quietly(self):
        """Earth Engine being unreachable must not take the answer down."""

        class OfflineEE(FakeEE):
            def ImageCollection(self, _name):
                raise ConnectionError("earth engine unreachable")

        weather = engine._sample_climate(OfflineEE(), PLACE, 6000.0, "rabi")
        assert weather.season_rainfall_mm is None
        assert weather.avg_temp_c is None
