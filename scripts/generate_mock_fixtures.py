#!/usr/bin/env python3
"""Record real API output as fixtures for the frontend's mock mode.

Why this exists: mock mode used to replay one hardcoded response, so picking
Nagpur showed Lucknow's soil and rabi crops. Rather than reimplement the ranker
in TypeScript just to make the mock believable, we run the real engine once per
district and season and record what it says.

That keeps one source of truth for agronomy, and it means mock mode is a
faithful recording rather than a fiction - if the ranker changes, you re-run
this and the mock changes with it.

Run with the API up:
    uvicorn apps.api.main:app --port 8000
    python scripts/generate_mock_fixtures.py

Output: data/seed/api-fixtures/generated/
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DISTRICTS = REPO_ROOT / "data" / "reference" / "districts.json"
OUT_DIR = REPO_ROOT / "data" / "seed" / "api-fixtures" / "generated"

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
SEASONS = ("kharif", "rabi", "zaid")
DEFAULT_AREA_HA = 1.0

# Recorded responses must be byte-stable across runs, or every regeneration
# shows up as a huge meaningless diff. Both of these change on every request.
STABLE_REQUEST_ID = "req_MOCK{suffix}"
STABLE_TIMESTAMP = "2026-08-17T12:00:00Z"


def post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def stabilise(body: dict, suffix: str) -> dict:
    body["request_id"] = STABLE_REQUEST_ID.format(suffix=suffix.replace("-", "").upper())
    body["generated_at"] = STABLE_TIMESTAMP
    return body


def main() -> int:
    with DISTRICTS.open(encoding="utf-8") as handle:
        districts = json.load(handle)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    index: dict[str, list[str]] = {}

    for state in districts["states"]:
        for district in state["districts"]:
            code = district["district_code"]
            location = {
                "type": "admin",
                "state_code": state["state_code"],
                "district_code": code,
            }

            # Conditions are season-independent, so record them once per district.
            summary = post("/api/v1/geo/field-summary", {"location": location})
            indices = post("/api/v1/geo/indices", {"location": location})
            (OUT_DIR / f"indices.{code}.json").write_text(
                json.dumps(indices, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            (OUT_DIR / f"field-summary.{code}.json").write_text(
                json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            written += 2

            seasons_with_crops: list[str] = []
            for season in SEASONS:
                try:
                    body = post(
                        "/api/v1/recommendations",
                        {
                            "location": location,
                            "season": season,
                            "area_ha": DEFAULT_AREA_HA,
                            "irrigation": "rainfed",
                            "limit": 5,
                        },
                    )
                except urllib.error.HTTPError as exc:
                    # A season with no calendared crops is a legitimate outcome,
                    # not a failure. Record nothing and let the mock 422 too.
                    print(f"  {code} {season}: {exc.code}, skipping")
                    continue

                body = stabilise(body, f"{code}{season}")
                (OUT_DIR / f"recommendations.{code}.{season}.json").write_text(
                    json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
                )
                seasons_with_crops.append(season)
                written += 1

            index[code] = seasons_with_crops
            print(f"  {code}: {', '.join(seasons_with_crops) or 'none'}")

    # The frontend reads this to know which combinations exist without probing.
    (OUT_DIR / "index.json").write_text(
        json.dumps({"districts": index, "generated_from": BASE_URL}, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"\nWrote {written + 1} files to {OUT_DIR.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
