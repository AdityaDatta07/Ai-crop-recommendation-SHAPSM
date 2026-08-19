"""Generate advisories across the demo districts so the crowding panel has data.

WHY THIS EXISTS
---------------
The crowding panel counts advisories this tool has issued. On a fresh clone
that count is zero, so the panel correctly says "not enough advisories yet" and
shows nothing — which is honest, and useless for a demo.

This script fills the store by running the REAL recommender over the seeded
districts. Nothing is fabricated: every row is genuine output of the same code
path a farmer's request goes through, and it can be regenerated, inspected and
disagreed with.

WHY THE INPUTS VARY
-------------------
The first version of this ran one identical request per district, and produced
a store in which one crop was ranked first 100% of the time. That number is
true and worthless: it measures the fact that I sent the same request twelve
times, not anything about the district.

Real users differ in plot size, water source and whether they have a soil card.
Those are the inputs that actually move the ranking, so the sweep varies them
across ranges that reflect Indian holdings, and takes whatever distribution
falls out. The spread is NOT tuned to produce a pleasing chart — if a district
genuinely comes out at 90% wheat, that is the answer, and it is a real finding
about this tool's advice rather than about wheat.

WHY THE ROWS ARE MARKED
-----------------------
Every advisory written here is flagged `seeded`. The panel reports how many of
its total came from this script, because a count that silently blended
generated advisories with real use would overstate how much the tool is
actually being consulted — the same species of overstatement the whole feature
was rebuilt to avoid.

IT REFUSES TO SEED FROM NOTHING
-------------------------------
The first run of this wrote 72 advisories in which every district produced an
identical ranking. The cause was not the sweep: Earth Engine was unconfigured,
the geo provider degraded to EMPTY conditions, and the ranker fell back to
season fit — which does not vary by district. Every advisory was real output of
real code and none of it described anywhere.

That is the failure mode this whole feature exists to avoid, arriving by the
back door. A store full of condition-free advisories renders as a confident
"ranked first in 8 of 12", and nothing on the panel would reveal that the 12
were computed from no soil, no rainfall and no temperature.

So the script checks `data_completeness` on the first advisory of every
district and stops if the conditions are hollow. Run with USE_MOCK_GEO=true, or
configure Earth Engine, or pass --force if you genuinely want the rows anyway.

USAGE
-----
    USE_MOCK_GEO=true python scripts/seed_advisories.py    # all districts
    python scripts/seed_advisories.py UP-LKO               # one district
    python scripts/seed_advisories.py --clear              # remove seeded rows
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.api.core.reference import load_reference  # noqa: E402
from apps.api.core.repository import DEFAULT_SQLITE_PATH, SqliteRepository  # noqa: E402
from apps.api.schemas import contract as api  # noqa: E402
from apps.api.services.recommendation_service import recommend  # noqa: E402

logging.basicConfig(level=logging.WARNING)

SEASONS = ("kharif", "rabi", "zaid")

#: Plot sizes in hectares. Weighted towards the small end because that is what
#: Indian landholding looks like: the 2015-16 Agriculture Census puts 86% of
#: holdings under 2 ha and the average at about 1.08 ha.
AREAS_HA = (0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.6, 2.0, 3.0, 4.0)

#: Every water source the contract allows. Rainfed twice because it is by far
#: the most common — roughly half of India's net sown area is unirrigated —
#: and a uniform sweep would overstate how many farmers have a tubewell.
IRRIGATION = ("rainfed", "rainfed", "canal", "tubewell", "drip")

#: Soil-card values, and None for the majority who do not bring one.
#: Below this, the advisory was computed from almost no measured conditions and
#: the ranking is season fit alone. Chosen to sit well under what a working
#: provider returns (mock gives 0.85 to 0.92, Earth Engine similar) and well
#: above what a total outage gives (0.0).
MIN_DATA_COMPLETENESS = 0.4

#: Soil-card values, and None for the majority who do not bring one.
SOIL_TESTS = (
    None,
    None,
    None,
    {"nitrogen_kg_ha": 180.0, "phosphorus_kg_ha": 12.0, "potassium_kg_ha": 190.0},
    {"nitrogen_kg_ha": 320.0, "phosphorus_kg_ha": 28.0, "potassium_kg_ha": 260.0},
)


def seeded_districts() -> list[tuple[str, str]]:
    """(state_code, district_code) for every district with a seed fixture."""
    reference = load_reference()
    pairs: list[tuple[str, str]] = []
    for state in reference.districts.get("states", []):
        for district in state.get("districts", []):
            pairs.append((state["state_code"], district["district_code"]))
    return pairs


def clear_seeded(path: Path) -> int:
    """Remove only the generated rows.

    Deliberately scoped to `seeded = 1`. A --clear that also dropped genuine
    advisories would destroy the very thing the panel is supposed to measure,
    and it would do it quietly.
    """
    with sqlite3.connect(path) as connection:
        cursor = connection.execute("DELETE FROM recommendation_results WHERE seeded = 1")
        return cursor.rowcount


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("districts", nargs="*", help="District codes; default is all seeded ones")
    parser.add_argument("--clear", action="store_true", help="Delete seeded rows and exit")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Seed even when conditions are hollow. You almost certainly do not want this.",
    )
    parser.add_argument(
        "--per-district",
        type=int,
        default=12,
        help="Advisories per district per season. Default 12, comfortably above "
        "the minimum the panel needs before it will report a share.",
    )
    args = parser.parse_args()

    path = Path(os.getenv("RESULTS_DB_PATH", "") or DEFAULT_SQLITE_PATH)
    repository = SqliteRepository(path)

    if args.clear:
        removed = clear_seeded(path)
        print(f"Removed {removed} seeded advisories from {path}")
        return 0

    reference = load_reference()
    pairs = seeded_districts()
    if args.districts:
        wanted = {code.upper() for code in args.districts}
        pairs = [p for p in pairs if p[1].upper() in wanted]
        if not pairs:
            print(f"No seeded district matches {sorted(wanted)}", file=sys.stderr)
            return 1

    written = 0
    failed = 0

    for state_code, district_code in pairs:
        for season in SEASONS:
            for index in range(args.per_district):
                # Deterministic rather than random: the same command produces
                # the same store, so a surprising number on the panel can be
                # reproduced and traced instead of argued about.
                request = api.RecommendationRequest(
                    location={
                        "type": "admin",
                        "state_code": state_code,
                        "district_code": district_code,
                    },
                    season=season,
                    area_ha=AREAS_HA[index % len(AREAS_HA)],
                    irrigation=IRRIGATION[index % len(IRRIGATION)],
                    soil_test=SOIL_TESTS[index % len(SOIL_TESTS)],
                    limit=5,
                )
                try:
                    result = recommend(request, reference, repository=repository)
                except Exception as error:  # noqa: BLE001
                    failed += 1
                    print(f"  ! {district_code}/{season}[{index}]: {error}", file=sys.stderr)
                    continue

                completeness = result.conditions.data_completeness
                if completeness < MIN_DATA_COMPLETENESS and not args.force:
                    print(
                        f"\nSTOPPING: {district_code}/{season} came back with "
                        f"data_completeness={completeness:.2f}.\n"
                        f"\nThe geo provider is returning little or nothing, so these "
                        f"advisories would be ranked on season fit alone and every "
                        f"district would look identical. The crowding panel would then "
                        f"present those counts as if they meant something.\n"
                        f"\nFix one of:\n"
                        f"  USE_MOCK_GEO=true python scripts/seed_advisories.py ...\n"
                        f"  configure Earth Engine credentials\n"
                        f"  --force, if you really want hollow rows\n"
                        f"\n{written} advisories were written before stopping; "
                        f"remove them with --clear.",
                        file=sys.stderr,
                    )
                    return 1

                repository.save(
                    result.request_id, result.model_dump(mode="json"), seeded=True
                )
                written += 1

        print(f"  {district_code}: done")

    print(f"\nWrote {written} seeded advisories to {path}")
    if failed:
        print(f"{failed} requests failed; see errors above", file=sys.stderr)
    print("Remove them again with: python scripts/seed_advisories.py --clear")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
