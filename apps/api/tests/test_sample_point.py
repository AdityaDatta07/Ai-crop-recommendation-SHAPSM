"""Where the satellite actually looks.

THE BUG THIS EXISTS TO CATCH
----------------------------
Every satellite reading in this app — soil, weather, NDVI, the whole crop
history — is taken from a buffer around `ResolvedLocation.centroid`. That
centroid was the DISTRICT record's centroid for all three location forms, so a
dropped pin and a carefully drawn boundary were both discarded and replaced
with the middle of the district, which is usually its main town.

Nothing failed. The readings were accurate; they were accurate about a city.
A plot near Lucknow came back with flat NDVI and "no crop grown" at high
confidence, and the map's draw-your-field feature was decorative.

These tests assert the sample point follows the farmer.
"""

from __future__ import annotations

import pytest

from services.geo.districts import resolve
from services.geo.types import Location

#: Farmland south-west of Lucknow, well clear of the city centroid.
FIELD_LON, FIELD_LAT = 80.83, 26.62

#: What data/reference/districts.json stores for Lucknow: the city.
DISTRICT_CENTROID = (80.94, 26.84)


class TestTheSamplePointFollowsTheFarmer:
    def test_a_dropped_pin_is_sampled_where_it_was_dropped(self):
        place = resolve(Location(type="point", lon=FIELD_LON, lat=FIELD_LAT), 1.0)
        assert place.centroid == (FIELD_LON, FIELD_LAT)
        assert place.centroid != DISTRICT_CENTROID

    def test_a_drawn_boundary_is_sampled_at_its_own_centre(self):
        ring = [
            [80.828, 26.618],
            [80.832, 26.618],
            [80.832, 26.622],
            [80.828, 26.622],
            [80.828, 26.618],
        ]
        place = resolve(Location(type="polygon", coordinates=[ring]), 1.0)
        lon, lat = place.centroid
        assert lon == pytest.approx(80.830, abs=0.002)
        assert lat == pytest.approx(26.620, abs=0.002)
        assert place.centroid != DISTRICT_CENTROID

    def test_a_district_selection_still_falls_back_to_the_district(self):
        """No pin, no boundary — the district centroid is genuinely all we have."""
        place = resolve(Location(type="admin", district_code="UP-LKO"), 1.0)
        assert place.centroid == DISTRICT_CENTROID

    def test_the_district_is_still_named_correctly_from_a_pin(self):
        """Keeping the farmer's point must not lose the administrative label."""
        place = resolve(Location(type="point", lon=FIELD_LON, lat=FIELD_LAT), 1.0)
        assert place.district_code == "UP-LKO"
        assert place.district_name == "Lucknow"

    def test_two_fields_in_one_district_sample_different_places(self):
        """The strong form: without this, every plot in a district was identical."""
        north = resolve(Location(type="point", lon=80.90, lat=26.95), 1.0)
        south = resolve(Location(type="point", lon=80.83, lat=26.62), 1.0)
        assert north.district_code == south.district_code
        assert north.centroid != south.centroid


class TestThePrecisionIsDeclared:
    """A district pick reads the district centroid, and must say so.

    Every satellite figure comes from a buffer around `centroid`. For an admin
    selection that centroid is the district's own — Lucknow's is [80.94, 26.84],
    the city. Soil, NDVI, crop history and the productivity comparison then all
    describe a town, rendered exactly like readings of a field.

    The symptom: a plot reported as growing no crop and sitting in the 17th
    percentile of surrounding farmland. Both figures correct. The plot was a
    city. Nothing on the page distinguished it from a real field.
    """

    def test_a_district_pick_is_marked_as_district_precision(self):
        place = resolve(Location(type="admin", district_code="UP-LKO"), 1.0)
        assert place.precision == "district"

    def test_a_dropped_pin_is_marked_as_a_point(self):
        place = resolve(Location(type="point", lon=FIELD_LON, lat=FIELD_LAT), 1.0)
        assert place.precision == "point"

    def test_a_drawn_boundary_is_marked_as_a_field(self):
        ring = [
            [80.828, 26.618],
            [80.832, 26.618],
            [80.832, 26.622],
            [80.828, 26.622],
            [80.828, 26.618],
        ]
        place = resolve(Location(type="polygon", coordinates=[ring]), 1.0)
        assert place.precision == "field"

    def test_the_api_carries_the_precision_to_the_client(self):
        from fastapi.testclient import TestClient

        from apps.api.main import app

        client = TestClient(app)
        body = client.post(
            "/api/v1/geo/field-summary",
            json={
                "location": {
                    "type": "admin",
                    "state_code": "UP",
                    "district_code": "UP-LKO",
                }
            },
        ).json()
        assert body["location_resolved"]["precision"] == "district"

    def test_the_notice_exists_and_is_translated(self):
        import json
        from pathlib import Path

        web = Path(__file__).resolve().parents[3] / "apps" / "web"
        component = web / "src" / "components" / "recommendation" / "precision-notice.tsx"
        assert component.exists()
        assert "precision !== 'district'" in component.read_text(encoding="utf-8")

        for locale in ("en", "hi"):
            path = web / "src" / "i18n" / f"{locale}.json"
            assert "district" in json.loads(path.read_text(encoding="utf-8"))["precision"]
