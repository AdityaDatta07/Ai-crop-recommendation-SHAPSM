"""The what-if calculator's premise, tested at the API.

The calculator does not compute anything. It re-asks the same question with one
input changed and shows what comes back. That only works if two things hold:

  1. The response carries the inputs it was computed from, or a reopened link
     has nothing to vary.
  2. Varying an input actually moves the answer.

Point 2 is the one worth testing. If area scaled linearly and nothing else, the
honest thing would have been a multiplication in the browser. These tests show
it does not: changing irrigation or nitrogen can reorder the ranking outright,
so the panel has to ask the server or it will show the old crop's money under a
new crop's name.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app

BASE = {
    "location": {"type": "admin", "state_code": "UP", "district_code": "UP-LKO"},
    "season": "kharif",
    "area_ha": 1.0,
    "irrigation": "rainfed",
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def post(client: TestClient, **overrides) -> dict:
    response = client.post("/api/v1/recommendations", json={**BASE, **overrides})
    assert response.status_code == 200, response.text
    return response.json()


class TestRequestEcho:
    def test_response_carries_the_inputs_it_was_computed_from(self, client):
        body = post(client, area_ha=2.5, irrigation="canal", previous_crop="WHEAT")
        echo = body["request_echo"]

        assert echo["area_ha"] == 2.5
        assert echo["irrigation"] == "canal"
        assert echo["season"] == "kharif"
        assert echo["previous_crop"] == "WHEAT"

    def test_echo_is_the_request_not_the_resolution(self, client):
        """area_ha echoes what was asked; location_resolved holds what we made of it."""
        body = post(client, area_ha=3.0)
        assert body["request_echo"]["area_ha"] == 3.0
        assert "district_name" in body["location_resolved"]

    def test_soil_test_round_trips(self, client):
        body = post(
            client,
            soil_test={
                "nitrogen_kg_ha": 300,
                "phosphorus_kg_ha": 40,
                "potassium_kg_ha": 250,
            },
        )
        assert body["request_echo"]["soil_test"]["nitrogen_kg_ha"] == 300

    def test_replaying_the_echo_reproduces_the_ranking(self, client):
        """The echo has to be a complete question, not a partial one.

        If replaying it gave a different answer, the calculator's "no change"
        baseline would disagree with the advisory printed above it.
        """
        first = post(client, area_ha=2.0, irrigation="canal", previous_crop="WHEAT")
        echo = first["request_echo"]

        replayed = client.post(
            "/api/v1/recommendations",
            json={
                "location": echo["location"],
                "season": echo["season"],
                "area_ha": echo["area_ha"],
                "irrigation": echo["irrigation"],
                "soil_test": echo["soil_test"],
                "previous_crop": echo["previous_crop"],
            },
        )
        assert replayed.status_code == 200

        order = lambda body: [r["crop_code"] for r in body["recommendations"]]
        assert order(replayed.json()) == order(first)


class TestInputsActuallyMoveTheAnswer:
    def test_area_scales_the_money(self, client):
        one = post(client, area_ha=1.0)["recommendations"][0]
        four = post(client, area_ha=4.0)["recommendations"][0]

        assert one["crop_code"] == four["crop_code"]
        margin_one = one["economics"]["net_margin"]
        margin_four = four["economics"]["net_margin"]
        if margin_one is None or margin_four is None:
            pytest.skip("top crop is unpriced in this district")

        # Four times the land, near enough four times the money.
        assert margin_four == pytest.approx(margin_one * 4, rel=0.02)

    def test_per_hectare_margin_does_not_move_with_area(self, client):
        """The per-hectare figure is a rate. If it scaled, it would be a total."""
        one = post(client, area_ha=1.0)["recommendations"][0]["economics"]
        four = post(client, area_ha=4.0)["recommendations"][0]["economics"]

        if one["margin_per_ha"] is None:
            pytest.skip("top crop is unpriced in this district")
        assert one["margin_per_ha"] == pytest.approx(four["margin_per_ha"], rel=0.01)

    def test_irrigation_changes_the_ranking(self, client):
        """Why this cannot be a browser multiplication.

        Water availability is scored, so the crop at the top is allowed to
        change. A client scaling the previous crop's margin would show the wrong
        crop's money.
        """
        rainfed = post(client, irrigation="rainfed")
        drip = post(client, irrigation="drip")

        rainfed_scores = {r["crop_code"]: r["score"] for r in rainfed["recommendations"]}
        drip_scores = {r["crop_code"]: r["score"] for r in drip["recommendations"]}

        shared = set(rainfed_scores) & set(drip_scores)
        assert shared, "no crops in common; cannot compare"
        assert any(
            rainfed_scores[code] != drip_scores[code] for code in shared
        ), "irrigation changed nothing — the calculator would be showing a dead control"

    def test_nitrogen_changes_the_ranking(self, client):
        poor = post(
            client,
            soil_test={"nitrogen_kg_ha": 80, "phosphorus_kg_ha": None, "potassium_kg_ha": None},
        )
        rich = post(
            client,
            soil_test={"nitrogen_kg_ha": 600, "phosphorus_kg_ha": None, "potassium_kg_ha": None},
        )

        poor_scores = {r["crop_code"]: r["score"] for r in poor["recommendations"]}
        rich_scores = {r["crop_code"]: r["score"] for r in rich["recommendations"]}

        shared = set(poor_scores) & set(rich_scores)
        assert any(poor_scores[code] != rich_scores[code] for code in shared), (
            "nitrogen changed nothing — either the slider is pointless or "
            "soil_test is not reaching the ranker"
        )

    def test_a_what_if_does_not_disturb_the_original(self, client):
        """Exploring must not rewrite the advisory the farmer was given."""
        original = post(client, area_ha=1.0)
        request_id = original["request_id"]

        post(client, area_ha=9.0)  # the what-if

        reread = client.get(f"/api/v1/recommendations/{request_id}")
        assert reread.status_code == 200
        assert reread.json()["request_echo"]["area_ha"] == 1.0
        assert [r["crop_code"] for r in reread.json()["recommendations"]] == [
            r["crop_code"] for r in original["recommendations"]
        ]
