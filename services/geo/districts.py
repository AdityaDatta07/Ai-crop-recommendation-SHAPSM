"""District lookup and coordinate resolution.

Loaded once from data/reference/districts.json. Coverage is deliberately narrow
in v1 - a point outside every known district raises rather than guessing, which
is what produces the contract's NO_DATA_FOR_LOCATION.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from services.geo.types import GeoUnavailable, InvalidGeometry, Location, ResolvedLocation

REFERENCE_PATH = Path(__file__).resolve().parents[2] / "data" / "reference" / "districts.json"

# Beyond this distance from any district centroid we admit we have no coverage
# rather than snapping to a district hundreds of kilometres away.
MAX_SNAP_DISTANCE_KM = 150.0

# api-contract.md 2.1 caps a drawn field at 100 ha. Pydantic enforces that on
# the DECLARED area_ha, but a polygon overrides the declared area with its own
# computed one - so without this check the cap is trivially bypassed by drawing
# a big box, and the economics scale straight up with it.
MAX_POLYGON_AREA_HA = 100.0


@dataclass(frozen=True)
class DistrictRecord:
    state_code: str
    state_name: str
    district_code: str
    district_name: str
    lon: float
    lat: float


@lru_cache(maxsize=1)
def load_districts() -> tuple[DistrictRecord, ...]:
    with REFERENCE_PATH.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    records: list[DistrictRecord] = []
    for state in payload["states"]:
        for district in state["districts"]:
            lon, lat = district["centroid"]
            records.append(
                DistrictRecord(
                    state_code=state["state_code"],
                    state_name=state["state_name"],
                    district_code=district["district_code"],
                    district_name=district["district_name"],
                    lon=float(lon),
                    lat=float(lat),
                )
            )
    return tuple(records)


@lru_cache(maxsize=1)
def _by_code() -> dict[str, DistrictRecord]:
    return {record.district_code: record for record in load_districts()}


def find_by_code(district_code: str) -> DistrictRecord | None:
    return _by_code().get(district_code)


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance. Good enough for centroid snapping."""
    radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(a))


def nearest_district(lon: float, lat: float) -> DistrictRecord:
    records = load_districts()
    nearest = min(records, key=lambda r: haversine_km(lon, lat, r.lon, r.lat))
    distance = haversine_km(lon, lat, nearest.lon, nearest.lat)

    if distance > MAX_SNAP_DISTANCE_KM:
        raise GeoUnavailable(
            f"No district coverage within {MAX_SNAP_DISTANCE_KM:.0f} km of "
            f"({lat:.4f}, {lon:.4f}). Nearest is {nearest.district_name} at {distance:.0f} km."
        )
    return nearest


def polygon_centroid(rings: list[list[list[float]]]) -> tuple[float, float]:
    """Centroid of the outer ring. Planar approximation, fine at field scale."""
    outer = rings[0]
    points = outer[:-1] if outer and outer[0] == outer[-1] else outer
    if not points:
        raise GeoUnavailable("Polygon has no coordinates.")
    lon = sum(point[0] for point in points) / len(points)
    lat = sum(point[1] for point in points) / len(points)
    return lon, lat


def _segments_cross(
    a1: tuple[float, float],
    a2: tuple[float, float],
    b1: tuple[float, float],
    b2: tuple[float, float],
) -> bool:
    """Proper intersection test, excluding shared endpoints.

    Adjacent edges of a ring always meet at a vertex; that is not a crossing.
    Only interiors touching counts.
    """

    def orient(p, q, r) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    d1, d2 = orient(b1, b2, a1), orient(b1, b2, a2)
    d3, d4 = orient(a1, a2, b1), orient(a1, a2, b2)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def is_self_intersecting(rings: list[list[list[float]]]) -> bool:
    """Does the outer ring cross itself?

    This matters more than it looks. The shoelace formula in polygon_area_ha
    computes a SIGNED area, so on a self-intersecting ring the lobes cancel:
    four points drawn as a square give the right answer, the same four drawn as
    a bowtie give zero. Tapping corners out of order on a phone is easy, and the
    resulting area silently scales every economics figure in the response.

    GeoJSON also requires simple polygons, so an intersecting ring is invalid
    input regardless of what our own maths does with it.
    """
    outer = rings[0]
    points = outer[:-1] if outer and outer[0] == outer[-1] else outer
    count = len(points)
    if count < 4:
        return False

    edges = [(tuple(points[i]), tuple(points[(i + 1) % count])) for i in range(count)]
    for i in range(count):
        # Skip self and the two adjacent edges, which legitimately share vertices.
        for j in range(i + 2, count):
            if i == 0 and j == count - 1:
                continue
            if _segments_cross(*edges[i], *edges[j]):
                return True
    return False


def polygon_area_ha(rings: list[list[list[float]]]) -> float:
    """Shoelace area on an equirectangular projection about the ring's centroid.

    Accurate to well under a percent at field scale, which is all the contract's
    100 ha cap needs, and avoids a geospatial dependency in the hot path.
    """
    outer = rings[0]
    points = outer[:-1] if outer and outer[0] == outer[-1] else outer
    if len(points) < 3:
        raise GeoUnavailable("Polygon needs at least three distinct vertices.")

    mean_lat = sum(point[1] for point in points) / len(points)
    metres_per_deg_lat = 111_320.0
    metres_per_deg_lon = 111_320.0 * math.cos(math.radians(mean_lat))

    projected = [(p[0] * metres_per_deg_lon, p[1] * metres_per_deg_lat) for p in points]
    total = 0.0
    for i in range(len(projected)):
        x1, y1 = projected[i]
        x2, y2 = projected[(i + 1) % len(projected)]
        total += x1 * y2 - x2 * y1

    return abs(total) / 2.0 / 10_000.0  # m^2 -> hectares


def resolve(location: Location, area_ha: float) -> ResolvedLocation:
    """Normalise any of the three location forms to a district and centroid.

    THE CENTROID IS WHERE WE SAMPLE, SO IT MUST BE THE FARMER'S FIELD
    -----------------------------------------------------------------
    Every satellite reading in this app is taken from a buffer around
    `centroid`. This function used to return the DISTRICT record's centroid for
    all three location types, which meant a dropped pin and a carefully drawn
    boundary were both thrown away and replaced with the middle of the
    district — usually its main town.

    The symptom was a plot in Lucknow reporting flat, low NDVI and "no crop
    grown", with high confidence. The reading was accurate. It was a reading of
    the city.

    So: the district record names the place, and only supplies the sample point
    when the farmer picked a district and gave us nothing more precise.
    """
    sample_point: tuple[float, float] | None = None

    if location.type == "admin":
        record = find_by_code(location.district_code or "")
        if record is None:
            raise GeoUnavailable(f"Unknown district code: {location.district_code!r}")

    elif location.type == "point":
        if location.lat is None or location.lon is None:
            raise GeoUnavailable("Point location is missing coordinates.")
        record = nearest_district(location.lon, location.lat)
        sample_point = (location.lon, location.lat)

    elif location.type == "polygon":
        if not location.coordinates:
            raise GeoUnavailable("Polygon location is missing geometry.")
        rings = [[list(p) for p in ring] for ring in location.coordinates]
        # The drawn boundary is a better area estimate than whatever was typed,
        # but it must still respect the documented limit.
        if is_self_intersecting(rings):
            raise InvalidGeometry(
                "The field boundary crosses itself. Redraw it so the outline "
                "does not overlap — the area cannot be measured otherwise."
            )
        area_ha = polygon_area_ha(rings)
        if area_ha > MAX_POLYGON_AREA_HA:
            raise InvalidGeometry(
                f"Polygon area of {area_ha:,.1f} ha exceeds the "
                f"{MAX_POLYGON_AREA_HA:.0f} ha limit."
            )
        lon, lat = polygon_centroid(rings)
        record = nearest_district(lon, lat)
        sample_point = (lon, lat)

    else:  # pragma: no cover - Pydantic rejects this at the edge
        raise GeoUnavailable(f"Unsupported location type: {location.type!r}")

    return ResolvedLocation(
        state_code=record.state_code,
        district_code=record.district_code,
        district_name=record.district_name,
        # The farmer's own point wins. The district centroid is the fallback
        # for an administrative selection, where it is genuinely all we have.
        centroid=sample_point or (record.lon, record.lat),
        area_ha=round(area_ha, 4),
        precision=(
            "field"
            if location.type == "polygon"
            else "point"
            if location.type == "point"
            else "district"
        ),
    )
