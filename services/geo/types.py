"""Domain types for the geo service.

These are plain dataclasses, deliberately not Pydantic. Contract enforcement
belongs at the HTTP edge in apps/api/schemas; this package should be usable
from a notebook or a script without dragging the web layer in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Sequence

LocationType = Literal["point", "admin", "polygon"]


@dataclass(frozen=True)
class Location:
    """The three location forms from the API contract, normalised into one type.

    Exactly one group of fields is populated, according to `type`. The contract
    keeps them as a tagged union for the wire; internally a single shape is
    easier to pass around than three.
    """

    type: LocationType
    lat: float | None = None
    lon: float | None = None
    state_code: str | None = None
    district_code: str | None = None
    coordinates: Sequence[Sequence[Sequence[float]]] | None = None  # GeoJSON rings


@dataclass(frozen=True)
class SoilConditions:
    texture: str | None = None
    ph: float | None = None
    organic_carbon_pct: float | None = None
    nitrogen_kg_ha: float | None = None
    phosphorus_kg_ha: float | None = None
    potassium_kg_ha: float | None = None
    source: str | None = None


@dataclass(frozen=True)
class WeatherConditions:
    annual_rainfall_mm: float | None = None
    season_rainfall_mm: float | None = None
    avg_temp_c: float | None = None
    source: str | None = None


@dataclass(frozen=True)
class Conditions:
    soil: SoilConditions = field(default_factory=SoilConditions)
    weather: WeatherConditions = field(default_factory=WeatherConditions)
    ndvi_current: float | None = None
    data_completeness: float = 0.0

    @property
    def is_degraded(self) -> bool:
        return self.data_completeness < 1.0


@dataclass(frozen=True)
class ResolvedLocation:
    state_code: str
    district_code: str
    district_name: str
    centroid: tuple[float, float]  # [lon, lat], GeoJSON order
    area_ha: float


class GeoUnavailable(Exception):
    """Raised only when a location cannot be resolved at all.

    Note what this is NOT raised for: a failure to sample soil or weather.
    Those degrade to null fields and a reduced completeness score, because a
    partial answer beats an error page. See architecture.md principle 2.
    """


class InvalidGeometry(Exception):
    """The geometry is well-formed JSON but not something we will act on.

    Distinct from GeoUnavailable: that means "we have no data there", which is
    a 422. This means "that input is out of bounds", which is a 400. The
    difference matters to the farmer - one is our gap, the other is fixable by
    redrawing.
    """
