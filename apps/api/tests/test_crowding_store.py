"""Counting advisories.

The panel's whole claim rests on this query. A miscount here does not raise or
look wrong — it produces a slightly different percentage, which is exactly the
kind of error nobody can see.

Both repository implementations are tested against the same expectations,
because the demo runs on SQLite and a deployment runs on Supabase, and a panel
that says something different depending on the backend is worse than one that
says nothing.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from apps.api.core.repository import MemoryRepository, SqliteRepository


def advisory(district: str, season: str, top_crop: str | None) -> dict:
    recommendations = []
    if top_crop:
        recommendations = [
            {"rank": 1, "crop_code": top_crop, "name": top_crop.title()},
            {"rank": 2, "crop_code": "OTHER", "name": "Other"},
        ]
    return {
        "location_resolved": {"district_code": district, "district_name": district},
        "request_echo": {"season": season},
        "recommendations": recommendations,
    }


@pytest.fixture(params=["sqlite", "memory"])
def repository(request, tmp_path):
    """Every test runs against both backends."""
    if request.param == "sqlite":
        return SqliteRepository(tmp_path / "results.db")
    return MemoryRepository()


def _id(suffix: str) -> str:
    # The Supabase schema requires >= 26 characters; keep test ids realistic.
    return f"req_{suffix}".ljust(26, "0")


class TestCounting:
    def test_it_counts_the_crop_ranked_first(self, repository):
        for i in range(3):
            repository.save(_id(f"w{i}"), advisory("UP-LKO", "rabi", "WHEAT"))
        counts, total, _ = repository.top_crop_counts("UP-LKO", "rabi")
        assert counts == {"WHEAT": 3}
        assert total == 3

    def test_it_does_not_count_crops_ranked_second(self, repository):
        """Counting every crop that appears would make five crops look
        universally recommended, since nearly every advisory lists five."""
        repository.save(_id("a"), advisory("UP-LKO", "rabi", "WHEAT"))
        counts, _, _ = repository.top_crop_counts("UP-LKO", "rabi")
        assert "OTHER" not in counts

    def test_districts_do_not_bleed_into_each_other(self, repository):
        repository.save(_id("a"), advisory("UP-LKO", "rabi", "WHEAT"))
        repository.save(_id("b"), advisory("MH-NGP", "rabi", "WHEAT"))
        _, total, _ = repository.top_crop_counts("UP-LKO", "rabi")
        assert total == 1

    def test_seasons_do_not_bleed_into_each_other(self, repository):
        """Kharif and rabi are different decisions. Pooling them would make the
        share describe a year rather than the season being planned."""
        repository.save(_id("a"), advisory("UP-LKO", "rabi", "WHEAT"))
        repository.save(_id("b"), advisory("UP-LKO", "kharif", "RICE"))
        counts, total, _ = repository.top_crop_counts("UP-LKO", "rabi")
        assert counts == {"WHEAT": 1}
        assert total == 1

    def test_an_advisory_with_no_recommendation_still_counts_in_the_total(
        self, repository
    ):
        """It is an advisory we issued. Dropping it from the denominator would
        inflate every share by pretending the request never happened."""
        repository.save(_id("a"), advisory("UP-LKO", "rabi", "WHEAT"))
        repository.save(_id("b"), advisory("UP-LKO", "rabi", None))
        counts, total, _ = repository.top_crop_counts("UP-LKO", "rabi")
        assert counts == {"WHEAT": 1}
        assert total == 2

    def test_an_empty_district_returns_zero_not_an_error(self, repository):
        counts, total, seeded = repository.top_crop_counts("XX-NONE", "rabi")
        assert (counts, total, seeded) == ({}, 0, 0)


class TestSeededRowsAreDistinguishable:
    def test_seeded_advisories_are_reported_separately(self, repository):
        repository.save(_id("real"), advisory("UP-LKO", "rabi", "WHEAT"))
        repository.save(_id("seed"), advisory("UP-LKO", "rabi", "WHEAT"), seeded=True)
        _, total, seeded = repository.top_crop_counts("UP-LKO", "rabi")
        assert total == 2
        assert seeded == 1

    def test_seeded_advisories_still_count_in_the_total(self, repository):
        """They are real output of the real recommender. Excluding them would
        make the panel's own numbers disagree with the store behind it."""
        repository.save(_id("seed"), advisory("UP-LKO", "rabi", "WHEAT"), seeded=True)
        counts, total, seeded = repository.top_crop_counts("UP-LKO", "rabi")
        assert counts == {"WHEAT": 1}
        assert total == 1 and seeded == 1

    def test_an_unseeded_store_reports_no_seeded_rows(self, repository):
        repository.save(_id("real"), advisory("UP-LKO", "rabi", "WHEAT"))
        _, _, seeded = repository.top_crop_counts("UP-LKO", "rabi")
        assert seeded == 0


class TestExpiry:
    def test_expired_advisories_are_not_counted(self, tmp_path):
        """A share computed over advisories the app would no longer serve
        describes a past nobody can open and check."""
        path = tmp_path / "results.db"
        repository = SqliteRepository(path)
        repository.save(_id("live"), advisory("UP-LKO", "rabi", "WHEAT"))

        stale = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        with sqlite3.connect(path) as connection:
            connection.execute(
                "INSERT INTO recommendation_results "
                "(request_id, payload, district_code, season, top_crop_code, "
                " seeded, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
                (
                    _id("old"),
                    json.dumps(advisory("UP-LKO", "rabi", "BARLEY")),
                    "UP-LKO",
                    "rabi",
                    "BARLEY",
                    stale,
                    stale,
                ),
            )

        counts, total, _ = repository.top_crop_counts("UP-LKO", "rabi")
        assert counts == {"WHEAT": 1}
        assert total == 1


class TestTheMigrationOnAnExistingDatabase:
    def test_an_old_table_gains_the_columns_and_is_backfilled(self, tmp_path):
        """Databases already on disk predate these columns.

        Without a backfill every stored advisory would count as season NULL and
        be invisible to the panel — understating the totals silently rather
        than failing, which is the harder kind of wrong to notice.
        """
        path = tmp_path / "results.db"
        now = datetime.now(timezone.utc)
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TABLE recommendation_results ("
                " request_id TEXT PRIMARY KEY, payload TEXT NOT NULL,"
                " district_code TEXT, created_at TEXT NOT NULL, expires_at TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO recommendation_results VALUES (?, ?, ?, ?, ?)",
                (
                    _id("old"),
                    json.dumps(advisory("UP-LKO", "rabi", "WHEAT")),
                    "UP-LKO",
                    now.isoformat(),
                    (now + timedelta(days=30)).isoformat(),
                ),
            )

        repository = SqliteRepository(path)
        counts, total, seeded = repository.top_crop_counts("UP-LKO", "rabi")
        assert counts == {"WHEAT": 1}, "pre-existing advisories were not backfilled"
        assert total == 1
        assert seeded == 0, "a pre-existing row is real use, not seeded"

    def test_opening_an_already_migrated_database_is_harmless(self, tmp_path):
        path = tmp_path / "results.db"
        first = SqliteRepository(path)
        first.save(_id("a"), advisory("UP-LKO", "rabi", "WHEAT"))

        second = SqliteRepository(path)
        counts, total, _ = second.top_crop_counts("UP-LKO", "rabi")
        assert counts == {"WHEAT": 1}
        assert total == 1


class TestPriceHistoryReportsWhatItHolds:
    """The layer the crowding tests could not see.

    `harvest_dip` is tested with lists handed to it directly, so it cannot
    notice that the thing SUPPLYING those lists returns empty ones. That gap is
    exactly where the "0 recorded prices from the rest of the year" falsehood
    lived: the analysis was correct about the data it was given, and the data
    it was given was wrong.
    """

    def _history(self, tmp_path):
        from apps.api.core.price_history import PriceHistory

        history = PriceHistory(tmp_path / "prices.db")
        # Everything in August, which is what a store looks like on a machine
        # that has been running for two days.
        for day in range(1, 21):
            history.record(
                "CHICKPEA", "UP-LKO", f"Mandi {day}", date(2026, 8, day), 5000 + day
            )
        return history

    def test_an_unusable_comparison_still_returns_the_prices_we_have(self, tmp_path):
        history = self._history(tmp_path)
        # April harvest: nothing recorded in April, plenty outside it.
        harvest, other, scope = history.harvest_month_comparison("CHICKPEA", 4, "UP-LKO")
        assert scope == "none", "there is no April data, so no comparison is possible"
        assert harvest == []
        assert len(other) == 20, (
            "the refusal discarded 20 observations it had just measured — the "
            "screen then reports having none"
        )

    def test_scope_is_none_so_nothing_mistakes_it_for_a_comparison(self, tmp_path):
        """The counts come back, but never labelled as a usable market."""
        _, _, scope = self._history(tmp_path).harvest_month_comparison("CHICKPEA", 4, "UP-LKO")
        assert scope == "none"

    def test_a_usable_comparison_still_works(self, tmp_path):
        history = self._history(tmp_path)
        for day in range(1, 21):
            history.record("CHICKPEA", "UP-LKO", f"Mandi {day}", date(2026, 4, day), 4000)
        harvest, other, scope = history.harvest_month_comparison("CHICKPEA", 4, "UP-LKO")
        assert scope == "district"
        assert len(harvest) == 20 and len(other) == 20

    def test_it_falls_back_to_every_district_and_says_so(self, tmp_path):
        """Pooling districts is genuinely useful and is a different claim.

        A nationwide harvest dip in onion is real information about onion. But
        a farmer in Nashik reading it as their own mandi has been misled, which
        is the same substitution `precision` exists to prevent on the location
        side — so the scope has to come back as "national", not "district".
        """
        from apps.api.core.price_history import PriceHistory

        history = PriceHistory(tmp_path / "prices.db")
        for day in range(1, 21):
            # Recorded against a DIFFERENT district than the one asked about.
            history.record("ONION", "MH-NGP", f"Mandi {day}", date(2026, 4, day), 800)
            history.record("ONION", "MH-NGP", f"Mandi {day}", date(2026, 9, day), 1400)

        harvest, other, scope = history.harvest_month_comparison("ONION", 4, "UP-LKO")
        assert scope == "national", "the local district has nothing; this is pooled data"
        assert len(harvest) == 20 and len(other) == 20

    def test_local_data_is_preferred_over_pooled_data(self, tmp_path):
        from apps.api.core.price_history import PriceHistory

        history = PriceHistory(tmp_path / "prices.db")
        for day in range(1, 21):
            history.record("ONION", "MH-NGP", f"Far {day}", date(2026, 4, day), 800)
            history.record("ONION", "MH-NGP", f"Far {day}", date(2026, 9, day), 1400)
            history.record("ONION", "UP-LKO", f"Near {day}", date(2026, 4, day), 900)
            history.record("ONION", "UP-LKO", f"Near {day}", date(2026, 9, day), 1500)

        harvest, _, scope = history.harvest_month_comparison("ONION", 4, "UP-LKO")
        assert scope == "district"
        assert all(price == 900 for price in harvest), "pooled prices leaked into a local answer"

    def test_the_whole_path_produces_a_truthful_sentence(self, tmp_path):
        """End to end: store -> comparison -> the params the UI renders."""
        from apps.api.services.crowding import harvest_dip

        harvest, other, scope = self._history(tmp_path).harvest_month_comparison(
            "CHICKPEA", 4, "UP-LKO"
        )
        result = harvest_dip(
            "CHICKPEA",
            harvest_month=4,
            harvest_month_prices=harvest,
            other_month_prices=other,
            scope=scope,
        )
        assert result.code == "harvest_month_not_seen_yet"
        assert result.params["other_seen"] == 20


class TestTheSuiteDoesNotWriteToTheRealStore:
    """Guards the conftest isolation.

    Without it, every test run added advisories to data/results.db and the
    crowding panel counted them: Lucknow rabi once read 1,393 advisories, of
    which 1,381 were pytest. Nothing failed — the panel just quietly described
    the test suite instead of the district.

    A fixture nobody checks is a fixture that gets removed in a refactor, so
    the isolation is asserted rather than assumed.
    """

    def test_the_results_path_is_redirected_away_from_the_repository(self):
        import os

        from apps.api.core.repository import DEFAULT_SQLITE_PATH

        configured = os.getenv("RESULTS_DB_PATH")
        assert configured, "RESULTS_DB_PATH is unset — the suite is writing to the real store"
        assert Path(configured).resolve() != DEFAULT_SQLITE_PATH.resolve()

    def test_posting_a_recommendation_leaves_the_real_store_untouched(self, client, lucknow_request):
        from apps.api.core.repository import DEFAULT_SQLITE_PATH

        def rows() -> int:
            if not DEFAULT_SQLITE_PATH.exists():
                return 0
            with sqlite3.connect(DEFAULT_SQLITE_PATH) as connection:
                return connection.execute(
                    "SELECT COUNT(*) FROM recommendation_results"
                ).fetchone()[0]

        before = rows()
        assert client.post("/api/v1/recommendations", json=lucknow_request).status_code == 200
        assert rows() == before, "a test request was written into data/results.db"


class TestTheCurrentAdvisoryIsNotInItsOwnTotal:
    def test_the_response_counts_only_advisories_already_stored(self, tmp_path, monkeypatch):
        """The router saves AFTER recommend() returns.

        If it saved first, every farmer would be the +1 that tipped their own
        district, and the total on screen would never match the store. This
        pins the ordering.
        """
        monkeypatch.setenv("USE_MOCK_GEO", "true")
        monkeypatch.setenv("RESULTS_DB_PATH", str(tmp_path / "results.db"))

        from apps.api.core.reference import load_reference
        from apps.api.schemas import contract as api
        from apps.api.services.recommendation_service import recommend

        repository = SqliteRepository(tmp_path / "results.db")
        request = api.RecommendationRequest(
            location={"type": "admin", "state_code": "UP", "district_code": "UP-LKO"},
            season="rabi",
            area_ha=1.0,
        )
        result = recommend(request, load_reference(), repository=repository)

        assert result.crowding, "no crowding rows produced"
        assert result.crowding[0].concentration.advisories_total == 0, (
            "the advisory being generated counted itself"
        )
