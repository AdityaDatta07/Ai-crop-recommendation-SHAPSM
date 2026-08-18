"""Reference data integrity.

These are the tests that stop provenance rotting. Every number the farmer sees
traces to a source, and if that stops being true the build should fail.
"""

from __future__ import annotations

import pytest

from apps.api.core.reference import REFERENCE_DIR, ReferenceDataError, load_reference


def test_every_economic_value_resolves_to_a_source(reference):
    for code, econ in reference.economics_raw.items():
        for value_key, source_key in (
            ("price_per_quintal", "price_source"),
            ("cost_a2fl_per_quintal", "cost_source"),
            ("yield_kg_per_ha", "yield_source"),
        ):
            if econ.get(value_key) is not None:
                source = reference.source_for(econ.get(source_key))
                assert source is not None, f"{code}.{value_key} has no resolvable source"
                assert source.citation, f"{code}.{value_key} source has no citation string"


def test_crops_and_economics_cover_the_same_crops(reference):
    assert set(reference.crops) == set(reference.economics_raw)


def test_agronomic_thresholds_are_internally_consistent(reference):
    """Optimal bands must sit inside absolute bands, or taper() misbehaves."""
    for code, crop in reference.crops.items():
        opt_lo, opt_hi = crop.ph_optimal
        abs_lo, abs_hi = crop.ph_absolute
        assert abs_lo <= opt_lo < opt_hi <= abs_hi, f"{code} pH bands are inconsistent"

        opt_lo, opt_hi = crop.temp_optimal_c
        abs_lo, abs_hi = crop.temp_absolute_c
        assert abs_lo <= opt_lo < opt_hi <= abs_hi, f"{code} temperature bands are inconsistent"

        low, high = crop.rainfall_mm
        assert 0 < low < high, f"{code} rainfall band is inconsistent"
        assert crop.duration_days > 0


def test_sowing_windows_do_not_straddle_new_year(reference):
    """calendar_service assumes this. If it stops holding, that code must change."""
    for code, crop in reference.crops.items():
        start = tuple(int(p) for p in crop.sowing_window.start.split("-"))
        end = tuple(int(p) for p in crop.sowing_window.end.split("-"))
        assert start <= end, f"{code} sowing window wraps the year; calendar_service cannot handle it"


def test_agronomy_source_is_flagged_provisional(reference):
    """A guard on honesty, not on correctness.

    While the thresholds are unverified this must stay provisional so the
    PROVISIONAL_AGRONOMY warning keeps firing. When a real ICAR reference
    replaces it, this test should be updated deliberately - not silently.
    """
    assert reference.agronomy_source.tier == "provisional"
    assert reference.agronomy_source.caveat


def test_districts_have_valid_centroids(reference):
    for state in reference.districts["states"]:
        for district in state["districts"]:
            lon, lat = district["centroid"]
            assert -180 <= lon <= 180 and -90 <= lat <= 90
            # Everything in scope is in India; a swapped lat/lon would show here.
            assert 68 <= lon <= 98, f"{district['district_code']} longitude looks swapped"
            assert 6 <= lat <= 38, f"{district['district_code']} latitude looks swapped"
