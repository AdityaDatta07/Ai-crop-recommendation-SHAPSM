from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.core.reference import load_reference
from apps.api.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "data" / "seed" / "api-fixtures"


@pytest.fixture(scope="session", autouse=True)
def _isolate_the_results_store(tmp_path_factory):
    """Keep the test suite out of data/results.db.

    Every test that posts to /recommendations writes a row, and without this the
    rows landed in the real store — the same file the running app uses. It was
    invisible for months because nothing read the store in aggregate.

    The district crowding panel does. After a few dozen test runs, Lucknow rabi
    reported 1,393 advisories, of which 1,381 were pytest. The figure was not
    wrong so much as measuring the wrong thing: it counted advisories the code
    issued, including to itself.

    Session-scoped and autouse, so it cannot be forgotten by a new test file.
    """
    import os

    store = tmp_path_factory.mktemp("results") / "results.db"
    previous = os.environ.get("RESULTS_DB_PATH")
    os.environ["RESULTS_DB_PATH"] = str(store)
    yield store
    if previous is None:
        os.environ.pop("RESULTS_DB_PATH", None)
    else:
        os.environ["RESULTS_DB_PATH"] = previous


@pytest.fixture(scope="session")
def reference():
    return load_reference()


@pytest.fixture()
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def fixture_json():
    def _load(name: str) -> dict:
        with (FIXTURES / f"{name}.json").open(encoding="utf-8") as handle:
            return json.load(handle)

    return _load


@pytest.fixture()
def lucknow_request():
    return {
        "location": {"type": "admin", "state_code": "UP", "district_code": "UP-LKO"},
        "season": "rabi",
        "area_ha": 1.5,
        "irrigation": "canal",
        "limit": 5,
    }
