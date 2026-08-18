from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.core.reference import load_reference
from apps.api.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "data" / "seed" / "api-fixtures"


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
