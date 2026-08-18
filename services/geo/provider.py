"""Backend selection and the public geo interface."""

from __future__ import annotations

import logging
import os

from datetime import date, datetime, timezone

from services.geo import districts, indices as indices_module, mock
from services.geo.indices import IndicesResult
from services.geo.types import Conditions, Location, ResolvedLocation

logger = logging.getLogger(__name__)


def _use_mock() -> bool:
    # Read at call time, not import time, so tests can flip it.
    return os.getenv("USE_MOCK_GEO", "true").strip().lower() in {"1", "true", "yes"}


def geo_backend_name() -> str:
    return "mock" if _use_mock() else "earthengine"


def resolve_admin(location: Location, area_ha: float) -> ResolvedLocation:
    """Turn any location form into a district, centroid and area.

    Raises GeoUnavailable if the location falls outside our coverage.
    """
    return districts.resolve(location, area_ha)


def get_conditions(place: ResolvedLocation) -> Conditions:
    """Sample soil, weather and vegetation for a resolved location.

    Never raises on a sampling failure. A backend that falls over returns an
    empty Conditions with completeness 0.0, and the caller decides what to tell
    the farmer. See architecture.md principle 2.
    """
    if _use_mock():
        return mock.get_conditions(place)

    from services.geo import earthengine

    try:
        return earthengine.get_conditions(place)
    except Exception:
        logger.exception(
            "Earth Engine sampling failed for %s; degrading to empty conditions",
            place.district_code,
        )
        return Conditions(data_completeness=0.0)


def get_indices(place: ResolvedLocation, today: date | None = None) -> IndicesResult:
    """Sentinel-2 spectral indices and NDVI history for a resolved location.

    Same failure contract as get_conditions: never raises. If Earth Engine is
    unreachable the caller still gets a result with null values and a source
    string that says why, because a map with no overlay beats an error page.
    """
    today = today or datetime.now(timezone.utc).date()

    if _use_mock():
        # Same NDVI the conditions panel shows - one measurement, one number.
        conditions = mock.get_conditions(place)
        return indices_module.mock_indices(place, today, conditions.ndvi_current)

    from services.geo import earthengine

    try:
        return earthengine.get_indices(place, today)
    except Exception:
        logger.exception("Earth Engine indices failed for %s; returning nulls", place.district_code)
        return IndicesResult(
            observed_on=None,
            cloud_cover_pct=None,
            indices=tuple(
                indices_module.IndexValue(
                    key=key,
                    name=str(spec["name"]),
                    value=None,
                    range_min=float(spec["range"][0]),
                    range_max=float(spec["range"][1]),
                    interpretation=indices_module.interpret(key, None),
                    formula=str(spec["formula"]),
                )
                for key, spec in indices_module.DEFINITIONS.items()
            ),
            history=(),
            source="Satellite imagery temporarily unavailable",
            tile_url_template=None,
        )
