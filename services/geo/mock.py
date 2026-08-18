"""Mock geo backend.

Serves the frozen fixtures for the two districts the demo script uses, and
deterministic synthetic values everywhere else so the app is explorable without
credentials.

The synthetic values are labelled as synthetic in the `source` string, which the
API passes through to the farmer's screen. Nothing here pretends to be measured
data - architecture.md principle 5 applies to mock data too, and a mock that
lies about its provenance is worse than no mock.
"""

from __future__ import annotations

import hashlib

from services.geo.types import Conditions, ResolvedLocation, SoilConditions, WeatherConditions

SYNTHETIC_SOURCE = "Synthetic mock data (USE_MOCK_GEO=true) — not measured"

TEXTURES = ("sandy loam", "loam", "clay loam", "clay", "silt loam")

# Districts with hand-set values, chosen so the demo beats in docs/demo-script.md
# are byte-for-byte reproducible and match data/seed/api-fixtures.
FIXTURE_DISTRICTS: dict[str, Conditions] = {
    # The healthy path.
    "UP-LKO": Conditions(
        soil=SoilConditions(
            texture="loam",
            ph=7.2,
            organic_carbon_pct=0.54,
            nitrogen_kg_ha=240,
            phosphorus_kg_ha=18,
            potassium_kg_ha=190,
            source="SoilGrids250m + Soil Health Card (mocked)",
        ),
        weather=WeatherConditions(
            annual_rainfall_mm=940,
            season_rainfall_mm=110,
            avg_temp_c=22.4,
            source="IMD gridded 1991-2020 normals (mocked)",
        ),
        ndvi_current=0.42,
        data_completeness=0.92,
    ),
    # The degraded path: alkaline clay, no nutrient data, no NDVI.
    "KA-BGK": Conditions(
        soil=SoilConditions(
            texture="clay",
            ph=8.1,
            organic_carbon_pct=None,
            nitrogen_kg_ha=None,
            phosphorus_kg_ha=None,
            potassium_kg_ha=None,
            source="SoilGrids250m (Soil Health Card unavailable for this district, mocked)",
        ),
        weather=WeatherConditions(
            annual_rainfall_mm=560,
            season_rainfall_mm=45,
            avg_temp_c=26.9,
            source="IMD gridded 1991-2020 normals (mocked)",
        ),
        ndvi_current=None,
        data_completeness=0.41,
    ),
}


def _seed(district_code: str) -> int:
    """Stable across processes, unlike hash()."""
    return int(hashlib.sha256(district_code.encode()).hexdigest()[:8], 16)


def _spread(seed: int, offset: int, low: float, high: float) -> float:
    """Deterministic value in [low, high) from the seed."""
    bucket = (seed >> (offset * 3)) % 1000
    return low + (high - low) * (bucket / 1000.0)


def synthesise(place: ResolvedLocation) -> Conditions:
    """Plausible, deterministic, and honest about being made up."""
    seed = _seed(place.district_code)
    lat = place.centroid[1]

    # Loosely latitude-aware so northern districts read cooler than southern
    # ones. This is a plausibility gesture, not a climate model.
    base_temp = 30.0 - (lat - 12.0) * 0.45

    return Conditions(
        soil=SoilConditions(
            texture=TEXTURES[seed % len(TEXTURES)],
            ph=round(_spread(seed, 1, 6.0, 8.4), 1),
            organic_carbon_pct=round(_spread(seed, 2, 0.25, 0.85), 2),
            nitrogen_kg_ha=round(_spread(seed, 3, 150, 320)),
            phosphorus_kg_ha=round(_spread(seed, 4, 9, 32)),
            potassium_kg_ha=round(_spread(seed, 5, 120, 280)),
            source=SYNTHETIC_SOURCE,
        ),
        weather=WeatherConditions(
            annual_rainfall_mm=round(_spread(seed, 6, 450, 1250)),
            season_rainfall_mm=round(_spread(seed, 7, 40, 260)),
            avg_temp_c=round(base_temp + _spread(seed, 8, -2.0, 2.0), 1),
            source=SYNTHETIC_SOURCE,
        ),
        ndvi_current=round(_spread(seed, 9, 0.18, 0.62), 2),
        data_completeness=0.85,
    )


def get_conditions(place: ResolvedLocation) -> Conditions:
    fixture = FIXTURE_DISTRICTS.get(place.district_code)
    return fixture if fixture is not None else synthesise(place)
