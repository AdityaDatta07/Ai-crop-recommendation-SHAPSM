"""Contract conformance.

These are the tests that earn their keep. apps/web is built against the fixtures
in data/seed/api-fixtures; apps/api is built against docs/api-contract.md. If
those two ever drift apart, the frontend breaks in a demo rather than in CI.

So: the same Pydantic models validate BOTH the frozen fixtures and the live
responses. One set of models, two sources of truth checked against it.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.api.schemas import contract as api
from services.ml.types import CropSpec  # noqa: F401  (kept for symmetry of imports)

# The closed set from api-contract.md §3.4. A factor outside this list would
# render as a raw identifier in the UI.
ALLOWED_FACTORS = {
    "soil_ph",
    "soil_texture",
    "nitrogen",
    "rainfall",
    "temperature",
    "irrigation",
    "market_price",
    "season_fit",
    "rotation",
}


class TestFixturesMatchTheContract:
    """The frontend's mock data must be shaped like the real thing."""

    @pytest.mark.parametrize(
        "name,model",
        [
            ("recommendations.success", api.RecommendationResponse),
            ("recommendations.low-confidence", api.RecommendationResponse),
            ("geo.field-summary", api.FieldSummaryResponse),
            ("meta.districts", api.DistrictsResponse),
            ("meta.crops", api.CropsResponse),
        ],
    )
    def test_fixture_validates(self, fixture_json, name, model):
        model.model_validate(fixture_json(name))

    def test_error_fixture_matches_the_envelope(self, fixture_json):
        body = fixture_json("recommendations.error-no-data")
        assert set(body) == {"error"}
        assert set(body["error"]) <= {"code", "message", "field", "request_id"}
        assert body["error"]["code"] == "NO_DATA_FOR_LOCATION"

    def test_fixture_economics_reconcile(self, fixture_json):
        """A fixture with maths that does not add up teaches the UI a lie."""
        body = fixture_json("recommendations.success")
        area = body["location_resolved"]["area_ha"]

        for item in body["recommendations"]:
            econ = item["economics"]
            if None in (
                econ["expected_yield_t_ha"],
                econ["expected_price_per_quintal"],
                econ["gross_revenue"],
            ):
                continue

            expected_gross = econ["expected_yield_t_ha"] * area * 10 * econ["expected_price_per_quintal"]
            assert econ["gross_revenue"] == pytest.approx(expected_gross, rel=0.01), item["crop_code"]

            expected_net = econ["gross_revenue"] - econ["input_cost_per_ha"] * area
            assert econ["net_margin"] == pytest.approx(expected_net, rel=0.01), item["crop_code"]
            assert econ["margin_per_ha"] == pytest.approx(econ["net_margin"] / area, rel=0.01)

    def test_fixture_crop_codes_exist_in_reference(self, fixture_json, reference):
        for item in fixture_json("recommendations.success")["recommendations"]:
            assert item["crop_code"] in reference.crops


class TestLiveResponsesMatchTheContract:
    def test_recommendation_response_validates(self, client, lucknow_request):
        api.RecommendationResponse.model_validate(
            client.post("/api/v1/recommendations", json=lucknow_request).json()
        )

    def test_field_summary_validates(self, client):
        api.FieldSummaryResponse.model_validate(
            client.post(
                "/api/v1/geo/field-summary",
                json={"location": {"type": "point", "lat": 26.8467, "lon": 80.9462}},
            ).json()
        )

    def test_meta_endpoints_validate(self, client):
        api.DistrictsResponse.model_validate(client.get("/api/v1/meta/districts").json())
        api.CropsResponse.model_validate(client.get("/api/v1/meta/crops").json())

    def test_prices_validates(self, client):
        api.PricesResponse.model_validate(client.get("/api/v1/prices/WHEAT").json())

    def test_reasons_use_only_documented_factors(self, client, lucknow_request):
        body = client.post("/api/v1/recommendations", json=lucknow_request).json()
        for item in body["recommendations"]:
            for reason in item["reasons"]:
                assert reason["factor"] in ALLOWED_FACTORS, reason["factor"]

    def test_reason_count_is_within_contract_bounds(self, client, lucknow_request):
        body = client.post("/api/v1/recommendations", json=lucknow_request).json()
        for item in body["recommendations"]:
            assert 2 <= len(item["reasons"]) <= 4, item["crop_code"]

    # Top-level fields added since the freeze, same reasoning as the per-crop list.
    ADDITIVE_TOP_LEVEL = {"comparison", "request_echo", "risk", "water", "crowding"}

    def test_live_response_has_the_same_top_level_keys_as_the_fixture(
        self, client, lucknow_request, fixture_json
    ):
        """Structural parity, checked directly rather than inferred."""
        live = client.post("/api/v1/recommendations", json=lucknow_request).json()
        expected = set(fixture_json("recommendations.success"))
        actual = set(live)

        assert expected - actual == set(), "live output dropped a contract field"
        assert actual - expected <= self.ADDITIVE_TOP_LEVEL

    # Fields added since the v1 freeze. Additive only: older clients ignore
    # them, and the frozen fixtures predate them. Anything NOT on this list
    # appearing in live output but missing from the fixture is real drift.
    ADDITIVE_SINCE_FREEZE = {"price_outlook", "counterfactuals", "attribution", "rotation", "rank_by_return"}

    # Same for nested objects that gained fields.
    ADDITIVE_ECONOMICS = {"input_cost_per_acre", "margin_per_acre"}

    def test_live_recommendation_has_the_same_keys_as_the_fixture(
        self, client, lucknow_request, fixture_json
    ):
        live = client.post("/api/v1/recommendations", json=lucknow_request).json()
        expected = set(fixture_json("recommendations.success")["recommendations"][0])
        actual = set(live["recommendations"][0])

        assert expected - actual == set(), "live output dropped a contract field"
        assert actual - expected <= self.ADDITIVE_SINCE_FREEZE, (
            "live output gained a field not declared additive — update the "
            "contract document and this list together"
        )

    def test_live_economics_reconcile(self, client, lucknow_request):
        """The same arithmetic check as the fixtures, against real output."""
        body = client.post("/api/v1/recommendations", json=lucknow_request).json()
        area = body["location_resolved"]["area_ha"]

        for item in body["recommendations"]:
            econ = item["economics"]
            if econ["net_margin"] is None:
                continue
            expected_net = econ["gross_revenue"] - econ["input_cost_per_ha"] * area
            assert econ["net_margin"] == pytest.approx(expected_net, abs=1), item["crop_code"]

    def test_null_economics_never_render_as_zero(self, client):
        """An unpriceable crop must return null, not 0. They mean different things."""
        body = client.post(
            "/api/v1/recommendations",
            json={
                "location": {"type": "admin", "state_code": "UP", "district_code": "UP-LKO"},
                "season": "rabi",
                "area_ha": 1.0,
                "constraints": {"exclude_crops": ["WHEAT", "MUSTARD", "CHICKPEA", "LENTIL", "BARLEY"]},
                "limit": 5,
            },
        ).json()

        unpriced = [
            item
            for item in body["recommendations"]
            if item["economics"]["expected_price_per_quintal"] is None
        ]
        assert unpriced, "expected at least one unpriceable crop in this selection"
        for item in unpriced:
            assert item["economics"]["gross_revenue"] is None
            assert item["economics"]["net_margin"] is None
            assert item["economics"]["price_source"] is None


class TestSchemaRejectsContractViolations:
    @pytest.mark.parametrize(
        "payload",
        [
            {"location": {"type": "point", "lat": 91, "lon": 80}, "season": "rabi", "area_ha": 1},
            {"location": {"type": "point", "lat": 26, "lon": 181}, "season": "rabi", "area_ha": 1},
            {"location": {"type": "point", "lat": 26, "lon": 80}, "season": "monsoon", "area_ha": 1},
            {"location": {"type": "point", "lat": 26, "lon": 80}, "season": "rabi", "area_ha": 0},
            {"location": {"type": "point", "lat": 26, "lon": 80}, "season": "rabi", "area_ha": 101},
            {
                "location": {"type": "point", "lat": 26, "lon": 80},
                "season": "rabi",
                "area_ha": 1,
                "limit": 11,
            },
            {
                "location": {
                    "type": "polygon",
                    "geometry": {"type": "Polygon", "coordinates": [[[80, 26], [81, 26], [81, 27]]]},
                },
                "season": "rabi",
                "area_ha": 1,
            },
        ],
    )
    def test_invalid_requests_are_rejected(self, payload):
        with pytest.raises(ValidationError):
            api.RecommendationRequest.model_validate(payload)

    def test_polygon_vertex_cap_is_enforced(self):
        ring = [[80.0 + i * 0.0001, 26.0] for i in range(250)]
        ring.append(ring[0])
        with pytest.raises(ValidationError):
            api.RecommendationRequest.model_validate(
                {
                    "location": {
                        "type": "polygon",
                        "geometry": {"type": "Polygon", "coordinates": [ring]},
                    },
                    "season": "rabi",
                    "area_ha": 1,
                }
            )
