"""Endpoint behaviour and the error envelope."""

from __future__ import annotations

import pytest


class TestHealth:
    def test_reports_backends(self, client):
        body = client.get("/health").json()
        assert body["status"] == "ok"
        assert body["geo_service"] in {"mock", "earthengine"}
        # "sqlite" was missing here when SQLite became the local default, so
        # this passed alone and failed in the suite depending on whether an
        # earlier test had left RESULTS_DB_PATH pointing somewhere writable.
        assert body["db"] in {"ok", "sqlite", "memory", "unreachable"}


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
            # Columns named, not positional: this test broke the day a column
            # was added, which is a false alarm about a real feature.
            connection.execute(
                "INSERT INTO recommendation_results "
                "(request_id, payload, district_code, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("req_old", json.dumps({}), "UP-LKO", stale, stale),
            )

        assert repo.get("req_old") is None

    def test_sqlite_is_preferred_over_memory_when_the_filesystem_allows_it(
        self, tmp_path, monkeypatch
    ):
        """Memory is a last resort, never a choice.

        Asserted against a filesystem we control rather than /health, because
        SQLite genuinely cannot take locks on some mounts (network shares, WSL)
        and the fallback to memory is correct behaviour there — just loud.
        """
        from apps.api.core.config import Settings
        from apps.api.core.repository import MemoryRepository, build_repository

        # monkeypatch, not os.environ directly. This used to set the variable and
        # then POP it in a finally block, which does not restore — it deletes.
        # Every test that ran afterwards fell back to the repository's default
        # path and wrote into the real data/results.db. Nothing failed, because
        # nothing read that store in aggregate until the crowding panel did, and
        # by then Lucknow rabi was reporting 1,393 advisories of which 1,381
        # were pytest.
        monkeypatch.setenv("RESULTS_DB_PATH", str(tmp_path / "results.db"))
        repository = build_repository(Settings(supabase_url="", supabase_service_role_key=""))
        assert not isinstance(repository, MemoryRepository)
        assert repository.health() == "sqlite"


class TestHarvestPriceOutlook:
    """Today's price is nearly irrelevant to a sowing decision — wheat sown in
    November is sold in April. The outlook projects to the selling month, and
    says plainly which kind of claim it is making."""

    def _outlook(self, client, crop_code="WHEAT"):
        body = client.post(
            "/api/v1/recommendations",
            json={
                "location": {"type": "admin", "state_code": "UP", "district_code": "UP-LKO"},
                "season": "rabi",
                "area_ha": 1.0,
                "limit": 10,
            },
        ).json()
        for item in body["recommendations"]:
            if item["crop_code"] == crop_code:
                return item["price_outlook"]
        return None

    def test_every_recommendation_carries_an_outlook(self, client):
        body = client.post(
            "/api/v1/recommendations",
            json={
                "location": {"type": "admin", "state_code": "UP", "district_code": "UP-LKO"},
                "season": "rabi",
                "area_ha": 1.0,
            },
        ).json()
        for item in body["recommendations"]:
            assert item["price_outlook"] is not None

    def test_harvest_month_is_in_the_future_not_today(self, client):
        outlook = self._outlook(client)
        assert outlook["harvest_month"] is not None
        # Rabi wheat is sown Nov and sold Mar-Apr; the month must not be sowing time.
        assert outlook["harvest_month"] > "2026-08"

    def test_without_history_it_reports_a_floor_not_a_forecast(self, client):
        """The honest default. Never dress an MSP floor as an expectation."""
        outlook = self._outlook(client)
        assert outlook["basis"] == "msp_floor"
        assert outlook["expected_per_quintal"] is None
        assert outlook["msp_floor_per_quintal"] is not None
        assert "not a forecast" in outlook["explanation"] or "floor" in outlook["explanation"]

    def test_seasonal_basis_needs_enough_observations(self):
        from datetime import date

        from apps.api.services.price_outlook import MIN_OBSERVATIONS_FOR_SEASONAL, build_outlook

        thin = build_outlook(
            crop_name="Wheat",
            harvest_start=date(2027, 3, 25),
            msp_floor=2585,
            current_price=2541,
            harvest_month_history=[2500] * (MIN_OBSERVATIONS_FOR_SEASONAL - 1),
        )
        assert thin.basis == "msp_floor"

        enough = build_outlook(
            crop_name="Wheat",
            harvest_start=date(2027, 3, 25),
            msp_floor=2585,
            current_price=2541,
            harvest_month_history=[2400, 2450, 2500, 2550, 2600, 2650, 2700, 2750],
        )
        assert enough.basis == "seasonal_history"
        assert enough.expected_per_quintal is not None
        assert enough.low_per_quintal <= enough.expected_per_quintal <= enough.high_per_quintal

    def test_outliers_do_not_define_the_range(self):
        """Quartiles, not min/max — one mis-keyed mandi entry must not set the band."""
        from datetime import date

        from apps.api.services.price_outlook import build_outlook

        outlook = build_outlook(
            crop_name="Wheat",
            harvest_start=date(2027, 3, 25),
            msp_floor=2585,
            current_price=2541,
            harvest_month_history=[1, 2500, 2520, 2540, 2560, 2580, 2600, 99999],
        )
        assert outlook.low_per_quintal > 100
        assert outlook.high_per_quintal < 90000

    def test_unpriced_crop_says_so_rather_than_inventing(self):
        from datetime import date

        from apps.api.services.price_outlook import build_outlook

        outlook = build_outlook(
            crop_name="Onion",
            harvest_start=date(2027, 2, 1),
            msp_floor=None,
            current_price=None,
            harvest_month_history=[],
        )
        assert outlook.basis == "none"
        assert outlook.expected_per_quintal is None


class TestPriceHistoryAccumulates:
    """data.gov.in serves only a current snapshot, so the only route to a real
    seasonal picture is keeping what we observe."""

    def test_records_and_reads_back_by_month(self, tmp_path):
        from datetime import date

        from apps.api.core.price_history import PriceHistory

        history = PriceHistory(tmp_path / "p.db")
        history.record("WHEAT", "UP-LKO", "Lucknow", date(2026, 3, 15), 2500)
        history.record("WHEAT", "UP-LKO", "Kanpur", date(2025, 3, 20), 2400)
        history.record("WHEAT", "UP-LKO", "Lucknow", date(2026, 8, 18), 2541)

        march = history.prices_in_month("WHEAT", 3)
        assert sorted(march) == [2400, 2500]  # both years, August excluded

    def test_re_recording_the_same_day_does_not_duplicate(self, tmp_path):
        from datetime import date

        from apps.api.core.price_history import PriceHistory

        history = PriceHistory(tmp_path / "p.db")
        for _ in range(3):
            history.record("WHEAT", "UP-LKO", "Lucknow", date(2026, 3, 15), 2500)
        assert len(history.prices_in_month("WHEAT", 3)) == 1

    def test_a_market_trading_below_msp_is_stated_not_hidden(self):
        """Live maize showed floor Rs 2410 and economics computed at Rs 2000.
        Two numbers on one screen with no explanation of the gap."""
        from datetime import date

        from apps.api.services.price_outlook import build_outlook

        outlook = build_outlook(
            crop_name="Maize",
            harvest_start=date(2027, 10, 3),
            msp_floor=2410,
            current_price=2000,
            harvest_month_history=[],
        )
        assert outlook.below_msp_by == 410
        assert "BELOW" in outlook.explanation
        assert "2000" in outlook.explanation and "2410" in outlook.explanation

    def test_no_gap_flagged_when_market_is_above_msp(self):
        from datetime import date

        from apps.api.services.price_outlook import build_outlook

        outlook = build_outlook(
            crop_name="Wheat",
            harvest_start=date(2027, 3, 25),
            msp_floor=2585,
            current_price=2700,
            harvest_month_history=[],
        )
        assert outlook.below_msp_by is None


class TestSowingWindowStatus:
    """Asked in August about kharif, the app showed a June 2027 sowing date and
    left the farmer to notice the year. Correct dates, silent about the year."""

    def _top(self, client, season):
        body = client.post(
            "/api/v1/recommendations",
            json={
                "location": {"type": "admin", "state_code": "UP", "district_code": "UP-LKO"},
                "season": season,
                "area_ha": 1.0,
            },
        ).json()
        return body, body["recommendations"][0]

    def test_every_crop_reports_a_window_status(self, client):
        body, _ = self._top(client, "rabi")
        for item in body["recommendations"]:
            assert item["calendar"]["window_status"] in {
                "open",
                "upcoming",
                "closed_this_year",
            }
            assert item["calendar"]["days_until_sowing"] is not None

    def test_a_closed_season_is_announced_not_implied(self, client):
        """August + kharif: sowing closed in July, dates shown are next year."""
        body, top = self._top(client, "kharif")
        if top["calendar"]["window_status"] != "closed_this_year":
            pytest.skip("kharif window still open at the current date")

        codes = {warning["code"] for warning in body["warnings"]}
        assert "SOWING_WINDOW_CLOSED" in codes

    def test_an_open_season_is_not_warned_about(self, client):
        body, top = self._top(client, "rabi")
        if top["calendar"]["window_status"] == "closed_this_year":
            pytest.skip("rabi window already closed at the current date")
        assert "SOWING_WINDOW_CLOSED" not in {w["code"] for w in body["warnings"]}

    def test_status_matches_the_dates_it_reports(self, client):
        """A status that disagrees with its own dates would be worse than none."""
        from datetime import date

        body, _ = self._top(client, "rabi")
        today = date.today()

        for item in body["recommendations"]:
            calendar = item["calendar"]
            start = date.fromisoformat(calendar["sowing_window"]["start"])
            end = date.fromisoformat(calendar["sowing_window"]["end"])

            if calendar["window_status"] == "open":
                assert start <= today <= end
            elif calendar["window_status"] == "upcoming":
                assert start > today
            else:
                assert start.year > today.year


class TestPerAcreFigures:
    """Indian farmers think in acres. Converting in the browser would put
    arithmetic in the one place this app must never do arithmetic."""

    def _economics(self, client, area_ha=2.5):
        body = client.post(
            "/api/v1/recommendations",
            json={
                "location": {"type": "admin", "state_code": "UP", "district_code": "UP-LKO"},
                "season": "rabi",
                "area_ha": area_ha,
            },
        ).json()
        return body, body["recommendations"][0]["economics"]

    def test_area_is_reported_in_both_units(self, client):
        body, _ = self._economics(client, area_ha=2.5)
        place = body["location_resolved"]
        assert place["area_ha"] == 2.5
        assert place["area_acres"] == pytest.approx(6.18, abs=0.01)

    def test_per_acre_is_consistent_with_per_hectare(self, client):
        from apps.api.services.economics import ACRES_PER_HECTARE

        _, economics = self._economics(client)
        if economics["margin_per_ha"] is None:
            pytest.skip("no priced crop in this result")

        assert economics["margin_per_acre"] == pytest.approx(
            economics["margin_per_ha"] / ACRES_PER_HECTARE, abs=1
        )
        assert economics["input_cost_per_acre"] == pytest.approx(
            economics["input_cost_per_ha"] / ACRES_PER_HECTARE, abs=1
        )

    def test_per_acre_is_smaller_than_per_hectare(self):
        """An acre is 0.4 ha, so per-acre figures must be lower. Catches an
        inverted conversion, which looks plausible and is badly wrong."""
        from apps.api.services.economics import compute

        result = compute(
            expected_yield_t_ha=4.0,
            published_yield_kg_per_ha=4000,
            cost_a2fl_per_quintal=1000,
            price_per_quintal=2500,
            area_ha=1.0,
            price_source="test",
            price_as_of=None,
        )
        assert result.margin_per_acre < result.margin_per_ha
        assert result.input_cost_per_acre < result.input_cost_per_ha

    def test_nulls_propagate_to_per_acre(self):
        from apps.api.services.economics import compute

        result = compute(
            expected_yield_t_ha=None,
            published_yield_kg_per_ha=None,
            cost_a2fl_per_quintal=None,
            price_per_quintal=None,
            area_ha=1.0,
            price_source=None,
            price_as_of=None,
        )
        assert result.margin_per_acre is None
        assert result.input_cost_per_acre is None


class TestCounterfactuals:
    """"Why" is only half the question. "What would I have to change" is the
    half a farmer can act on."""

    def _crop(self, client, crop_code):
        body = client.post(
            "/api/v1/recommendations",
            json={
                "location": {"type": "admin", "state_code": "KA", "district_code": "KA-BGK"},
                "season": "rabi",
                "area_ha": 1.0,
                "limit": 10,
            },
        ).json()
        return next(
            (item for item in body["recommendations"] if item["crop_code"] == crop_code), None
        )

    def test_every_recommendation_gets_the_field(self, client):
        body = client.post(
            "/api/v1/recommendations",
            json={
                "location": {"type": "admin", "state_code": "KA", "district_code": "KA-BGK"},
                "season": "rabi",
                "area_ha": 1.0,
            },
        ).json()
        for item in body["recommendations"]:
            assert "counterfactuals" in item

    def test_advice_only_when_this_crop_actually_improves(self):
        """Regression: the search advised REDUCING nitrogen for chickpea.

        Chickpea is a legume — its nitrogen score is 1.0 regardless — so cutting
        soil nitrogen left it untouched while hurting the cereals around it, and
        its rank rose. A rank gain from harming rivals is not advice.
        """
        from services.ml import Constraints, RankingInput, RulesRanker
        from services.ml.counterfactual import find_counterfactuals

        from apps.api.core.reference import load_reference

        reference = load_reference()
        rabi = reference.crops_for_season("rabi")
        conditions = RankingInput(
            ph=8.1,
            texture="clay",
            nitrogen_kg_ha=140,
            avg_temp_c=22.4,
            season_rainfall_mm=110,
            irrigation="rainfed",
            data_completeness=0.9,
        )
        ranker = RulesRanker()

        for crop_code in [crop.crop_code for crop in rabi]:
            for item in find_counterfactuals(
                ranker, conditions, rabi, Constraints(), crop_code
            ):
                if item.kind == "threshold":
                    assert item.score_gain > 0, (
                        f"{crop_code}: suggested a change that does not improve it "
                        f"({item.message})"
                    )

    def test_suggested_changes_are_physically_reachable(self):
        """No advising a two-point pH swing or 500 kg/ha of nitrogen."""
        from services.ml import Constraints, RankingInput, RulesRanker
        from services.ml.counterfactual import ACTIONABLE, find_counterfactuals

        from apps.api.core.reference import load_reference

        reference = load_reference()
        rabi = reference.crops_for_season("rabi")
        conditions = RankingInput(
            ph=8.1,
            texture="clay",
            nitrogen_kg_ha=140,
            avg_temp_c=22.4,
            season_rainfall_mm=110,
            irrigation="rainfed",
            data_completeness=0.9,
        )

        for crop_code in [crop.crop_code for crop in rabi]:
            for item in find_counterfactuals(
                RulesRanker(), conditions, rabi, Constraints(), crop_code
            ):
                if item.kind != "threshold" or item.factor == "irrigation":
                    continue
                current = float(item.current_value.split()[0])
                target = float(item.target_value.split()[0])
                limit = float(ACTIONABLE[item.factor]["max_change"])
                assert abs(target - current) <= limit + 1e-9

    def test_climate_is_never_suggested_as_changeable(self):
        """You cannot amend the weather; offering to is noise dressed as advice."""
        from services.ml.counterfactual import ACTIONABLE

        assert "temperature" not in ACTIONABLE
        assert "rainfall" not in ACTIONABLE

    def test_a_hopeless_crop_says_so_instead_of_inventing_a_lever(self, client):
        potato = self._crop(client, "POTATO")
        if potato is None:
            pytest.skip("potato not returned for this district")
        for item in potato["counterfactuals"]:
            if item["kind"] == "limiting":
                assert "Nothing you can realistically change" in item["message"]

    def test_attribution_sums_to_the_score(self, client):
        """For a weighted sum these ARE the Shapley values, so they must add up
        exactly. A gap would mean the explanation is hiding part of the score."""
        body = client.post(
            "/api/v1/recommendations",
            json={
                "location": {"type": "admin", "state_code": "UP", "district_code": "UP-LKO"},
                "season": "rabi",
                "area_ha": 1.0,
            },
        ).json()

        for item in body["recommendations"]:
            attribution = item["attribution"]
            assert attribution, "every recommendation needs its score broken down"
            total = sum(row["contribution"] for row in attribution)
            assert total == pytest.approx(item["score"], abs=0.005), (
                f"{item['crop_code']}: contributions sum to {total} but score is "
                f"{item['score']}"
            )

    def test_contribution_and_headroom_are_complementary(self, client):
        """Each factor's earned share plus what it left behind is its full weight."""
        body = client.post(
            "/api/v1/recommendations",
            json={
                "location": {"type": "admin", "state_code": "KA", "district_code": "KA-BGK"},
                "season": "rabi",
                "area_ha": 1.0,
            },
        ).json()

        for item in body["recommendations"]:
            for row in item["attribution"]:
                assert row["contribution"] >= 0
                assert row["headroom"] >= 0
                # score = contribution / (contribution + headroom), give or take
                span = row["contribution"] + row["headroom"]
                if span > 0.001:
                    assert row["score"] == pytest.approx(row["contribution"] / span, abs=0.01)

    def test_attribution_is_ordered_by_contribution(self, client):
        body = client.post(
            "/api/v1/recommendations",
            json={
                "location": {"type": "admin", "state_code": "UP", "district_code": "UP-LKO"},
                "season": "rabi",
                "area_ha": 1.0,
            },
        ).json()
        for item in body["recommendations"]:
            values = [row["contribution"] for row in item["attribution"]]
            assert values == sorted(values, reverse=True)


class TestComparisonView:
    """Last season's crop against this season's recommendation.

    Both sides are valued by the same engine on the same field, so the only
    difference is the crop. That is the whole point: we ask for a crop name and
    nothing else, rather than a form of remembered yields and prices that would
    create a second, unreconcilable source of truth.
    """

    def _request(self, previous=None, season="rabi"):
        payload = {
            "location": {"type": "admin", "state_code": "UP", "district_code": "UP-LKO"},
            "season": season,
            "area_ha": 2.0,
        }
        if previous:
            payload["previous_crop"] = previous
        return payload

    def test_absent_when_not_asked(self, client):
        body = client.post("/api/v1/recommendations", json=self._request()).json()
        assert body.get("comparison") is None

    def test_both_sides_are_valued(self, client):
        body = client.post("/api/v1/recommendations", json=self._request("WHEAT")).json()
        comparison = body["comparison"]
        assert comparison["previous"]["crop_code"] == "WHEAT"
        assert comparison["recommended"]["crop_code"] == body["recommendations"][0]["crop_code"]
        assert comparison["verdict"]

    def test_difference_is_recommended_minus_previous(self, client):
        body = client.post("/api/v1/recommendations", json=self._request("WHEAT")).json()
        comparison = body["comparison"]
        if comparison["margin_difference"] is None:
            pytest.skip("one side unpriced")
        assert comparison["margin_difference"] == (
            comparison["recommended"]["net_margin"] - comparison["previous"]["net_margin"]
        )

    def test_growing_the_best_crop_already_is_said_plainly(self, client):
        """No manufactured reason to switch when there isn't one.

        Updated when rotation scoring landed. Naming last season's crop now
        penalises repeating it, so the crop that tops the list WITHOUT a
        previous crop may not top it once one is given — which is the feature
        working, not a regression. The claim worth holding is narrower: when
        the engine does still put last season's crop first, it says so plainly
        instead of inventing a reason to switch.
        """
        body = client.post("/api/v1/recommendations", json=self._request()).json()
        best = body["recommendations"][0]["crop_code"]

        body = client.post("/api/v1/recommendations", json=self._request(best)).json()
        comparison = body["comparison"]

        if comparison["recommended"]["crop_code"] != best:
            pytest.skip("rotation moved it off the top, which is the intended behaviour")

        assert comparison["same_crop"] is True
        assert comparison["margin_difference"] == 0
        assert "No change needed" in comparison["verdict"]

    def test_repeating_last_seasons_crop_is_penalised(self, client):
        """The point of rotation scoring, stated as a test.

        Continuous cereal is a real agronomic problem — soil-borne disease and
        specialised pests accumulate with nothing to break the cycle. Telling
        the app what grew here last season must therefore push that same crop
        DOWN the list, not leave it untouched.
        """
        neutral = client.post("/api/v1/recommendations", json=self._request()).json()
        best = neutral["recommendations"][0]["crop_code"]
        before = next(
            item["score"] for item in neutral["recommendations"] if item["crop_code"] == best
        )

        repeated = client.post("/api/v1/recommendations", json=self._request(best)).json()
        after = next(
            (item["score"] for item in repeated["recommendations"] if item["crop_code"] == best),
            None,
        )
        if after is None:
            return  # Pushed clean out of the top five, which is the strong form.

        assert after < before, "naming last season's crop did not penalise repeating it"

    def test_a_legume_predecessor_helps_rather_than_hurts(self, client):
        """The other side of the same rule: rotation is not only a penalty."""
        after_cereal = client.post(
            "/api/v1/recommendations", json=self._request("WHEAT")
        ).json()
        after_legume = client.post(
            "/api/v1/recommendations", json=self._request("CHICKPEA")
        ).json()

        def score_of(body, code):
            return next(
                (i["score"] for i in body["recommendations"] if i["crop_code"] == code), None
            )

        # Mustard is neither a legume nor in the same family as either, so the
        # only thing that changes between these two calls is what preceded it.
        cereal_side = score_of(after_cereal, "MUSTARD")
        legume_side = score_of(after_legume, "MUSTARD")
        if cereal_side is None or legume_side is None:
            pytest.skip("mustard not in the top five for this field")

        assert legume_side > cereal_side, "following a legume should score better"

    def test_a_more_profitable_previous_crop_is_admitted(self, client):
        """The recommendation is agronomic. If last year's crop pays better,
        say so — burying it would be selling rather than advising."""
        body = client.post("/api/v1/recommendations", json=self._request("WHEAT")).json()
        comparison = body["comparison"]
        if comparison["margin_difference"] is None or comparison["margin_difference"] >= 0:
            pytest.skip("recommendation also pays better here")
        assert "would earn about" in comparison["verdict"]
        assert "Weigh the risk against the return" in comparison["verdict"]

    def test_out_of_season_previous_crop_is_handled(self, client):
        """Rice cannot grow in rabi here; comparing anyway would be nonsense."""
        body = client.post("/api/v1/recommendations", json=self._request("RICE")).json()
        comparison = body["comparison"]
        assert comparison["previous"]["rank"] is None
        assert "not suited" in comparison["verdict"]

    def test_unpriced_previous_crop_does_not_fabricate_a_difference(self, client):
        body = client.post("/api/v1/recommendations", json=self._request("POTATO")).json()
        comparison = body["comparison"]
        if comparison["previous"]["net_margin"] is not None:
            pytest.skip("potato priced in this run")
        assert comparison["margin_difference"] is None
        assert "cannot be compared" in comparison["verdict"]

    def test_unknown_crop_code_is_ignored_not_an_error(self, client):
        response = client.post(
            "/api/v1/recommendations", json=self._request("NOTACROP")
        )
        assert response.status_code == 200
        assert response.json().get("comparison") is None
