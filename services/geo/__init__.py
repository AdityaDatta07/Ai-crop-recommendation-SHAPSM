"""Geospatial service.

Public interface, and the only thing the rest of the system may depend on:

    get_conditions(location) -> Conditions
    resolve_admin(location, area_ha) -> ResolvedLocation

Whether that data comes from Earth Engine or from fixtures is this package's
business and nobody else's. `USE_MOCK_GEO=true` switches the backend.
"""

from services.geo.indices import HistoryPoint, IndexValue, IndicesResult
from services.geo.provider import (
    geo_backend_name,
    get_conditions,
    get_indices,
    resolve_admin,
)
from services.geo.types import (
    Conditions,
    GeoUnavailable,
    InvalidGeometry,
    Location,
    ResolvedLocation,
    SoilConditions,
    WeatherConditions,
)

__all__ = [
    "get_conditions",
    "get_indices",
    "IndicesResult",
    "IndexValue",
    "HistoryPoint",
    "resolve_admin",
    "geo_backend_name",
    "Conditions",
    "GeoUnavailable",
    "InvalidGeometry",
    "Location",
    "ResolvedLocation",
    "SoilConditions",
    "WeatherConditions",
]
