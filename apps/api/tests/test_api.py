"""Endpoint behaviour and the error envelope."""

from __future__ import annotations

import pytest


class TestHealth:
    def test_reports_backends(self, client):
        body = client.get("/health").json()
        assert body["status"] == "ok"
        assert body["geo_service"] in {"mock", "earthengine"}
        assert body["db"] in {"ok", "memory", "unreachable"}


class TestRequestId:
    def test_set_on_success(self, client, lucknow_request):
        response = client.post("/api/v1/recommendations", json=lucknow_request)
        assert response.headers.get("X-Request-Id")

    def test_set_on_failure_too(self, client):
        """Contract §5 says every response, which is exactly when it matters."""
        response = client.post("/api/v1/recommendations", json={"season": "rabi"})
        assert response.status_code == 400
        assert response.headers.get("X-Request-Id")

    def test_response_body_request_id_matches_header(self, client, lucknow_request):
        response = client.post("/api/v1/recommendations", json=lucknow_request)
        assert response.json()["request_id"] == response.headers["X-Request-Id"]


class TestErrorEnvelope:
    @pytest.mark.parametrize(
        "payload,status,code",
        [
            (
                {"location": {"type": "point", "lat": 999, "lon": 80}, "season": "rabi", "area_ha": 1},
                400,
                "VALIDATION_ERROR",
            ),
            (
                {
                    "location": {"type": "admin", "state_code": "UP", "district_code": "UP-LKO"},
                    "season": "rabi",
                    "area_ha": 500,
                },
                400,
                "VALIDATION_ERROR",
            ),
            (
                {
                    "location": {"type": "admin", "state_code": "XX", "district_code": "XX-ZZZ"},
                    "season": "rabi",
                    "area_ha": 1,
                },
                422,
                "NO_DATA_FOR_LOCATION",
            ),
            (
                {"location": {"type": "point", "lat": 5.0, "lon": 70.0}, "season": "rabi", "area_ha": 1},
                422,
                "NO_DATA_FOR_LOCATION",
            ),
        ],
    )
    def test_shape_is_identical_for_every_failure(self, client, payload, status, code):
        response = client.post("/api/v1/recommendations", json=payload)
        assert response.status_code == status

        body = response.json()
        assert set(body) == {"error"}
        assert body["error"]["code"] == code
        assert body["error"]["message"]
        assert body["error"]["request_id"]

    def test_missing_result_is_not_found(self, client):
        response = client.get("/api/v1/recommendations/req_01ABCDEFGHIJKLMNOPQRSTUVWX")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_unknown_crop_code_is_not_found(self, client):
        assert client.get("/api/v1/prices/NOTACROP").json()["error"]["code"] == "NOT_FOUND"


class TestRecommendations:
    def test_ranks_are_dense_and_ordered(self, client, lucknow_request):
        items = client.post("/api/v1/recommendations", json=lucknow_request).json()["recommendations"]
        assert [item["rank"] for item in items] == list(range(1, len(items) + 1))
        scores = [item["score"] for item in items]
        assert scores == sorted(scores, reverse=True)

    def test_respects_the_limit(self, client, lucknow_request):
        body = client.post(
            "/api/v1/recommendations", json={**lucknow_request, "limit": 2}
        ).json()
        assert len(body["recommendations"]) <= 2

    def test_honours_exclusions(self, client, lucknow_request):
        body = client.post(
            "/api/v1/recommendations",
            json={**lucknow_request, "constraints": {"exclude_crops": ["WHEAT", "MUSTARD"]}},
        ).json()
        returned = {item["crop_code"] for item in body["recommendations"]}
        assert not returned & {"WHEAT", "MUSTARD"}

    def test_unknown_request_fields_are_ignored_not_rejected(self, client, lucknow_request):
        """Contract §1. This is what lets us add fields without breaking clients."""
        response = client.post(
            "/api/v1/recommendations", json={**lucknow_request, "future_field": "whatever"}
        )
        assert response.status_code == 200

    def test_replay_returns_the_same_result(self, client, lucknow_request):
        created = client.post("/api/v1/recommendations", json=lucknow_request).json()
        replayed = client.get(f"/api/v1/recommendations/{created['request_id']}").json()
        assert replayed["request_id"] == created["request_id"]
        assert [item["crop_code"] for item in replayed["recommendations"]] == [
            item["crop_code"] for item in created["recommendations"]
        ]

    def test_polygon_area_overrides_the_declared_area(self, client):
        """The drawn boundary is better evidence than a typed number."""
        response = client.post(
            "/api/v1/recommendations",
            json={
                "location": {
                    "type": "polygon",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [80.940, 26.840],
                                [80.945, 26.840],
                                [80.945, 26.845],
                                [80.940, 26.845],
                                [80.940, 26.840],
                            ]
                        ],
                    },
                },
                "season": "rabi",
                "area_ha": 1.0,
            },
        )
        assert response.status_code == 200
        assert response.json()["location_resolved"]["area_ha"] != 1.0

    def test_warnings_always_present(self, client, lucknow_request):
        assert "warnings" in client.post("/api/v1/recommendations", json=lucknow_request).json()


class TestDegradedPath:
    """The scenario worth demoing: missing data, honest output."""

    @pytest.fixture()
    def degraded(self, client):
        return client.post(
            "/api/v1/recommendations",
            json={
                "location": {"type": "admin", "state_code": "KA", "district_code": "KA-BGK"},
                "season": "rabi",
                "area_ha": 0.8,
                "irrigation": "rainfed",
            },
        ).json()

    def test_still_returns_recommendations(self, degraded):
        assert degraded["recommendations"]

    def test_confidence_drops(self, degraded):
        assert all(item["confidence"] == "low" for item in degraded["recommendations"])

    def test_gaps_are_named_in_warnings(self, degraded):
        codes = {warning["code"] for warning in degraded["warnings"]}
        assert "LOW_DATA_COMPLETENESS" in codes
        assert "PARTIAL_SOIL_DATA" in codes

    def test_provisional_agronomy_is_always_disclosed(self, client, lucknow_request):
        body = client.post("/api/v1/recommendations", json=lucknow_request).json()
        assert "PROVISIONAL_AGRONOMY" in {w["code"] for w in body["warnings"]}


class TestMeta:
    def test_districts_filterable_by_state(self, client):
        body = client.get("/api/v1/meta/districts", params={"state_code": "UP"}).json()
        assert len(body["states"]) == 1
        assert body["states"][0]["state_code"] == "UP"

    def test_crop_codes_are_stable_join_keys(self, client):
        crops = client.get("/api/v1/meta/crops").json()["crops"]
        codes = [crop["crop_code"] for crop in crops]
        assert len(codes) == len(set(codes))
        assert all(code == code.upper() for code in codes)


class TestPolygonAreaCap:
    """Regression: a drawn polygon bypassed the documented 100 ha limit.

    Pydantic caps the DECLARED area_ha, but a polygon replaces that with its own
    computed area afterwards. A 44,205 ha box was accepted and produced a net
    margin of about Rs 194 crore - a number that would have been shown to a
    farmer, and to a judge.
    """

    def _polygon(self, half_degrees: float) -> dict:
        lon, lat = 80.94, 26.84
        ring = [
            [lon - half_degrees, lat - half_degrees],
            [lon + half_degrees, lat - half_degrees],
            [lon + half_degrees, lat + half_degrees],
            [lon - half_degrees, lat + half_degrees],
            [lon - half_degrees, lat - half_degrees],
        ]
        return {
            "location": {"type": "polygon", "geometry": {"type": "Polygon", "coordinates": [ring]}},
            "season": "rabi",
            "area_ha": 1.0,
        }

    def test_oversized_polygon_is_rejected(self, client):
        response = client.post("/api/v1/recommendations", json=self._polygon(0.1))
        assert response.status_code == 400
        body = response.json()["error"]
        assert body["code"] == "INVALID_LOCATION"
        assert body["field"] == "location.geometry"

    def test_reasonable_polygon_is_still_accepted(self, client):
        response = client.post("/api/v1/recommendations", json=self._polygon(0.002))
        assert response.status_code == 200
        assert response.json()["location_resolved"]["area_ha"] <= 100

    def test_field_summary_enforces_the_same_cap(self, client):
        """The cap has to hold on every path that resolves a polygon."""
        response = client.post(
            "/api/v1/geo/field-summary",
            json={"location": self._polygon(0.1)["location"]},
        )
        assert response.status_code == 400


class TestSelfIntersectingPolygon:
    """Regression: a bowtie boundary reported a nonsense area.

    polygon_area_ha is a signed shoelace sum, so a ring that crosses itself has
    its lobes cancel — four points as a square measure 123.92 ha, the same four
    as a bowtie measure 0.00 ha. Tapping corners out of order on a phone is easy,
    and the resulting area scaled every economics figure in the response.
    """

    BOWTIE = [
        [80.940, 26.840],
        [80.945, 26.840],
        [80.940, 26.845],
        [80.945, 26.845],
        [80.940, 26.840],
    ]

    def _payload(self, ring):
        return {
            "location": {"type": "polygon", "geometry": {"type": "Polygon", "coordinates": [ring]}},
            "season": "rabi",
            "area_ha": 1.0,
        }

    def test_bowtie_is_rejected(self, client):
        response = client.post("/api/v1/recommendations", json=self._payload(self.BOWTIE))
        assert response.status_code == 400
        body = response.json()["error"]
        assert body["code"] == "INVALID_LOCATION"
        assert "crosses itself" in body["message"]

    def test_simple_ring_with_the_same_points_is_accepted(self, client):
        square = [
            [80.940, 26.840],
            [80.945, 26.840],
            [80.945, 26.845],
            [80.940, 26.845],
            [80.940, 26.840],
        ]
        response = client.post("/api/v1/recommendations", json=self._payload(square))
        assert response.status_code == 200
        assert response.json()["location_resolved"]["area_ha"] > 0

    def test_field_summary_enforces_it_too(self, client):
        response = client.post(
            "/api/v1/geo/field-summary",
            json={"location": self._payload(self.BOWTIE)["location"]},
        )
        assert response.status_code == 400


class TestNdviIsConsistentAcrossPanels:
    """Regression: the same screen showed NDVI 0.18 and 0.39 for one field.

    conditions.ndvi_current and the indices endpoint measure the same thing.
    Two mock generators produced two answers, and contradictory numbers on one
    page undermine every other figure on it.
    """

    def test_conditions_and_indices_agree(self, client):
        location = {"type": "admin", "state_code": "MH", "district_code": "MH-NGP"}

        summary = client.post("/api/v1/geo/field-summary", json={"location": location}).json()
        indices = client.post("/api/v1/geo/indices", json={"location": location}).json()

        from_conditions = summary["conditions"]["ndvi_current"]
        from_indices = next(i["value"] for i in indices["indices"] if i["key"] == "ndvi")
        assert from_conditions == from_indices

    def test_unavailable_ndvi_propagates_instead_of_being_invented(self, client):
        """Bagalkot's imagery is clouded out. Every derived index must say so.

        The first fix conflated 'caller supplied nothing' with 'the value is
        known to be unavailable', so a field with no NDVI got a plausible 0.556.
        """
        location = {"type": "admin", "state_code": "KA", "district_code": "KA-BGK"}

        summary = client.post("/api/v1/geo/field-summary", json={"location": location}).json()
        assert summary["conditions"]["ndvi_current"] is None

        indices = client.post("/api/v1/geo/indices", json={"location": location}).json()
        for index in indices["indices"]:
            assert index["value"] is None, f"{index['key']} invented a value"
        assert indices["observed_on"] is None


class TestSoilHealthCardInput:
    """Farmer-supplied NPK. No satellite measures plant-available nutrients, so
    the card is the only real source for them."""

    def _request(self, **soil):
        return {
            "location": {"type": "admin", "state_code": "UP", "district_code": "UP-LKO"},
            "season": "rabi",
            "area_ha": 1.0,
            **({"soil_test": soil} if soil else {}),
        }

    def test_supplied_values_override_the_sampled_ones(self, client):
        body = client.post(
            "/api/v1/recommendations",
            json=self._request(nitrogen_kg_ha=280, phosphorus_kg_ha=22, potassium_kg_ha=210),
        ).json()
        soil = body["conditions"]["soil"]
        assert soil["nitrogen_kg_ha"] == 280
        assert soil["phosphorus_kg_ha"] == 22
        assert soil["potassium_kg_ha"] == 210

    def test_the_card_is_credited_as_a_source(self, client):
        body = client.post(
            "/api/v1/recommendations", json=self._request(nitrogen_kg_ha=280)
        ).json()
        assert "Soil Health Card" in body["conditions"]["soil"]["source"]

    def test_completeness_rises_with_each_value(self, client):
        none = client.post("/api/v1/recommendations", json=self._request()).json()
        one = client.post(
            "/api/v1/recommendations", json=self._request(nitrogen_kg_ha=280)
        ).json()
        three = client.post(
            "/api/v1/recommendations",
            json=self._request(nitrogen_kg_ha=280, phosphorus_kg_ha=22, potassium_kg_ha=210),
        ).json()

        a = none["conditions"]["data_completeness"]
        b = one["conditions"]["data_completeness"]
        c = three["conditions"]["data_completeness"]
        assert a <= b <= c
        assert c <= 1.0

    def test_a_partial_card_is_accepted(self, client):
        """One value is better than none; do not demand all three."""
        response = client.post("/api/v1/recommendations", json=self._request(nitrogen_kg_ha=280))
        assert response.status_code == 200
        assert response.json()["conditions"]["soil"]["nitrogen_kg_ha"] == 280

    def test_omitting_it_entirely_still_works(self, client):
        assert client.post("/api/v1/recommendations", json=self._request()).status_code == 200

    def test_absurd_values_are_rejected(self, client):
        """Bounds catch a decimal slip, not honest agronomic variation."""
        for bad in ({"nitrogen_kg_ha": 99999}, {"phosphorus_kg_ha": -5}):
            response = client.post("/api/v1/recommendations", json=self._request(**bad))
            assert response.status_code == 400
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_nitrogen_factor_actually_uses_the_supplied_value(self, client):
        """The point of asking: a poor reading must change the reasoning."""
        rich = client.post(
            "/api/v1/recommendations", json=self._request(nitrogen_kg_ha=320)
        ).json()
        poor = client.post(
            "/api/v1/recommendations", json=self._request(nitrogen_kg_ha=60)
        ).json()

        def nitrogen_details(body):
            return [
                reason["detail"]
                for item in body["recommendations"]
                for reason in item["reasons"]
                if reason["factor"] == "nitrogen"
            ]

        assert nitrogen_details(rich) != nitrogen_details(poor) or [
            item["score"] for item in rich["recommendations"]
        ] != [item["score"] for item in poor["recommendations"]]


class TestResultsSurviveRestart:
    """Regression: results lived in memory, so every /r/<id> link died on
    restart — including mid-demo, exactly when you would reopen one."""

    def test_sqlite_round_trips_a_result(self, tmp_path):
        from apps.api.core.repository import SqliteRepository

        repo = SqliteRepository(tmp_path / "results.db")
        repo.save("req_01TEST0000000000000000001", {"request_id": "x", "recommendations": []})

        # A NEW instance on the same file: this is what a restart looks like.
        reopened = SqliteRepository(tmp_path / "results.db")
        assert reopened.get("req_01TEST0000000000000000001") is not None

    def test_missing_id_returns_none(self, tmp_path):
        from apps.api.core.repository import SqliteRepository

        assert SqliteRepository(tmp_path / "r.db").get("req_nope") is None

    def test_expired_results_are_not_returned(self, tmp_path):
        import json
        import sqlite3
        from datetime import datetime, timedelta, timezone

        from apps.api.core.repository import SqliteRepository

        path = tmp_path / "results.db"
        repo = SqliteRepository(path)
        stale = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

        with sqlite3.connect(path) as connection:
            connection.execute(
                "INSERT INTO recommendation_results VALUES (?, ?, ?, ?, ?)",
                ("req_old", json.dumps({}), "UP-LKO", stale, stale),
            )

        assert repo.get("req_old") is None

    def test_sqlite_is_preferred_over_memory_when_the_filesystem_allows_it(self, tmp_path):
        """Memory is a last resort, never a choice.

        Asserted against a filesystem we control rather than /health, because
        SQLite genuinely cannot take locks on some mounts (network shares, WSL)
        and the fallback to memory is correct behaviour there — just loud.
        """
        import os

        from apps.api.core.config import Settings
        from apps.api.core.repository import MemoryRepository, build_repository

        os.environ["RESULTS_DB_PATH"] = str(tmp_path / "results.db")
        try:
            repository = build_repository(Settings(supabase_url="", supabase_service_role_key=""))
            assert not isinstance(repository, MemoryRepository)
            assert repository.health() == "sqlite"
        finally:
            os.environ.pop("RESULTS_DB_PATH", None)
