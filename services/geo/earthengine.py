"""Google Earth Engine backend.

Implemented but NOT verified: this code has never run against a real Earth
Engine project, because that needs a service account only the project owner can
create. Treat every function here as untested until someone runs it with
credentials. The mock path is what the test suite covers.

Setup:

  1. Create a Google Cloud project and enable the Earth Engine API.
  2. Register the project at https://code.earthengine.google.com/register
     (free for research and non-commercial use).
  3. Create a service account, grant it the "Earth Engine Resource Viewer" role,
     and download its JSON key.
  4. Point GEE_PRIVATE_KEY_PATH at the file, or put the base64 of it in
     GEE_SERVICE_ACCOUNT_KEY_B64 (better for Render, which has no filesystem
     you would want to trust with a key).
  5. Set GEE_PROJECT_ID and USE_MOCK_GEO=false.

The rule this module must never break: sampling failures degrade, they do not
raise. A cloud-covered field, a quota error and a cold start all return nulls
with a reduced completeness score. Only provider.py's blanket except is the
safety net, and relying on it means losing the reason.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import tempfile
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

from services.geo.types import ProductivitySample
from services.geo.indices import (
    DEFINITIONS,
    HistoryPoint,
    IndexValue,
    IndicesResult,
    interpret,
)
from services.geo.types import Conditions, ResolvedLocation, SoilConditions, WeatherConditions

logger = logging.getLogger(__name__)

# Sentinel-2 surface reflectance, harmonised across the 2022 processing change.
S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
# Soil properties: OpenLandMap, 250 m, in the public Earth Engine catalogue.
#
# The first attempt used projects/soilgrids-isric/*, which returned null for
# every sample at every geometry size — that path is not readable by an ordinary
# service account. OpenLandMap is public, documented, and gives texture class
# directly instead of making us infer it from clay and sand fractions.
#
# Band b0 is the 0 cm depth slice in each of these.
OLM_PH = "OpenLandMap/SOL/SOL_PH-H2O_USDA-4C1A2A_M/v02"
OLM_SOC = "OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02"
OLM_CLAY = "OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02"
OLM_SAND = "OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02"
OLM_TEXTURE = "OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02"

# USDA texture classes as coded by OpenLandMap, mapped onto the vocabulary
# data/reference/crops.yaml uses in texture_preferred.
USDA_TEXTURE_CLASSES = {
    1: "clay",
    2: "silty clay",
    3: "sandy clay",
    4: "clay loam",
    5: "silty clay loam",
    6: "sandy clay loam",
    7: "loam",
    8: "silt loam",
    9: "sandy loam",
    10: "silt",
    11: "loamy sand",
    12: "sandy",
}

# How far back to look for a usable, mostly cloud-free acquisition.
LOOKBACK_DAYS = 45
MAX_CLOUD_PCT = 40
# Sentinel-2 red/NIR are 10 m; SWIR is 20 m. Sample at 20 m so every band is
# native or better and no index is silently resampled up.
SAMPLE_SCALE_M = 20
HISTORY_MONTHS = 24

# Climate, from the public Earth Engine catalogue.
#
# CHIRPS: 5 km daily precipitation from 1981, station-corrected. Built for
# exactly this — rainfall over the global tropics, and well validated in India.
# ERA5-Land: 11 km reanalysis temperature. Coarser than the soil rasters, but
# temperature varies slowly over space so that matters far less than for soil.
CHIRPS_DAILY = "UCSB-CHG/CHIRPS/DAILY"
ERA5_LAND_MONTHLY = "ECMWF/ERA5_LAND/MONTHLY_AGGR"

# Climate normals need a stable baseline, not last year's weather. The WMO
# convention is a 30-year window; we use the most recent full decades available
# across both products.
NORMALS_START = "1994-01-01"
NORMALS_END = "2024-01-01"

# Fields the contract expects that no wired source provides: nitrogen,
# phosphorus and potassium. No satellite measures plant-available NPK — it is a
# laboratory measurement, and pretending otherwise would be the exact dishonesty
# this project is built to avoid. Counted against completeness so the number on
# screen reflects what is actually missing.
UNSOURCED_FIELDS = 3


#: Exceptions that mean OUR code is wrong, not that Earth Engine is unwell.
#:
#: The sampling blocks below catch broadly on purpose — a satellite service
#: being unreachable must degrade, never crash, per architecture.md principle 2.
#: But that same net caught a NameError from a parameter I forgot to thread
#: through, and reported it to farmers as "no rainfall reading for this field".
#: A bug that presents as missing data is a bug you ship.
#:
#: These re-raise so they fail where they can be seen.
BUGS_NOT_OUTAGES = (NameError, AttributeError, TypeError, KeyError, IndexError)


SEASON_MONTHS = {
    "kharif": (6, 9),    # June-September, the monsoon
    "rabi": (10, 2),     # October-February, the dry winter
    "zaid": (3, 5),      # March-May, the hot short season
}


def _season_window(today: date, season: str | None = None) -> tuple[int, int]:
    """(start_month, end_month) for the season being planned for.

    `season` is what the FARMER selected and must win. Falling back to the
    calendar was a real bug: asking for rabi in August returned the monsoon
    window, so a rabi plan was costed against 859 mm of kharif rain instead of
    the ~60 mm that actually falls between October and February. Every rabi
    rainfall score was inflated and the water budget told wheat growers they
    needed no irrigation at all.

    The calendar remains the fallback for callers with no season to offer,
    such as the field-summary endpoint.
    """
    if season and season.lower() in SEASON_MONTHS:
        return SEASON_MONTHS[season.lower()]

    month = today.month
    if 6 <= month <= 9:
        return 6, 9      # kharif
    if month >= 10 or month <= 2:
        return 10, 2     # rabi
    return 3, 5          # zaid


class EarthEngineNotConfigured(RuntimeError):
    pass


def _key_json() -> dict | None:
    """Service account key from the base64 env var, or from a file path.

    Order matters and so does forgiveness. A malformed base64 value used to
    shadow a perfectly good key file and fail with "Incorrect padding" — which
    says nothing about the real cause. A .env comment leaking into the value is
    enough to trigger it, and that is not the user's mistake to debug.

    So: try base64, and if it is not valid base64 of valid JSON, fall through to
    the file rather than raising.
    """
    encoded = os.getenv("GEE_SERVICE_ACCOUNT_KEY_B64", "").strip()
    if encoded:
        try:
            key = json.loads(base64.b64decode(encoded, validate=True))
            if isinstance(key, dict) and key.get("private_key"):
                return key
            logger.warning(
                "GEE_SERVICE_ACCOUNT_KEY_B64 decoded but is not a service-account "
                "key; falling back to GEE_PRIVATE_KEY_PATH."
            )
        except (binascii.Error, ValueError, UnicodeDecodeError):
            logger.warning(
                "GEE_SERVICE_ACCOUNT_KEY_B64 is set (%d chars) but is not valid "
                "base64 JSON — is a .env comment leaking into the value? "
                "Falling back to GEE_PRIVATE_KEY_PATH.",
                len(encoded),
            )

    path = os.getenv("GEE_PRIVATE_KEY_PATH", "").strip()
    if path:
        candidate = Path(path)
        if not candidate.is_absolute():
            # Paths in .env are written relative to the repo root, not to the
            # working directory the server happens to be started from.
            candidate = REPO_ROOT / path
        if candidate.exists():
            with candidate.open(encoding="utf-8") as handle:
                return json.load(handle)
        logger.warning("GEE_PRIVATE_KEY_PATH points at %s, which does not exist", candidate)

    return None


@lru_cache(maxsize=1)
def initialise():
    """Authenticate once per process. Raises if not configured."""
    try:
        import ee
    except ImportError as exc:  # pragma: no cover
        raise EarthEngineNotConfigured(
            "earthengine-api is not installed. Add it to requirements.txt, or "
            "keep USE_MOCK_GEO=true."
        ) from exc

    key = _key_json()
    project = os.getenv("GEE_PROJECT_ID", "").strip()
    if key is None or not project:
        raise EarthEngineNotConfigured(
            "Earth Engine needs GEE_PROJECT_ID and either GEE_SERVICE_ACCOUNT_KEY_B64 "
            "or GEE_PRIVATE_KEY_PATH."
        )

    # ServiceAccountCredentials wants a file, so materialise one that is deleted
    # on process exit. The key never touches the repo or a persistent volume.
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(key, handle)
        key_path = handle.name

    credentials = ee.ServiceAccountCredentials(key["client_email"], key_path)
    ee.Initialize(credentials, project=project)
    logger.info("Earth Engine initialised for project %s", project)
    return ee


def _geometry(ee, place: ResolvedLocation):
    """A point becomes a buffer sized to the plot, so we sample the field.

    A 1 ha square is 100 m on a side, so a radius of sqrt(area/pi) approximates
    the plot without needing its actual boundary. When a drawn polygon exists the
    caller should pass it instead - see the TODO in get_conditions.
    """
    lon, lat = place.centroid
    radius_m = max(30.0, (place.area_ha * 10_000 / 3.14159) ** 0.5)
    return ee.Geometry.Point([lon, lat]).buffer(radius_m)


def _mask_clouds_factory(ee):
    """The SCL cloud mask, shared by the eager and server-side paths."""

    def mask_clouds(image):
        scl = image.select("SCL")
        clear = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))
        return image.updateMask(clear).divide(10_000).copyProperties(
            image, image.propertyNames()
        )

    return mask_clouds


def _masked_s2(ee, geometry, start: date, end: date):
    """Cloud-masked Sentinel-2 collection over a window."""
    def mask_clouds(image):
        # Scene Classification Layer: 3 cloud shadow, 8 medium-probability cloud,
        # 9 high-probability cloud, 10 cirrus. Drop all four.
        scl = image.select("SCL")
        clear = (
            scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))
        )
        # SR bands are scaled by 10000; convert to reflectance so the index
        # formulas match their textbook definitions.
        return image.updateMask(clear).divide(10_000).copyProperties(image, image.propertyNames())

    return (
        ee.ImageCollection(S2_COLLECTION)
        .filterBounds(geometry)
        .filterDate(str(start), str(end))
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_CLOUD_PCT))
        .map(mask_clouds)
    )


#: How far around the plot counts as "the land around you". Large enough to
#: contain a few hundred fields, small enough to share this plot's soil,
#: rainfall and market. The district would be better in principle, but the
#: reference data holds centroids and no district polygons.
NEIGHBOURHOOD_RADIUS_M = 10_000

#: Coarser than the plot scale: 10 km of 10 m pixels is 1e6 pixels and Earth
#: Engine will refuse or silently downsample. 60 m still resolves a field.
NEIGHBOURHOOD_SCALE_M = 60

#: A pixel only enters the comparison if it ever looked like a growing crop.
#: Without this the distribution fills with roads, roofs and water, the median
#: collapses, and every real field is flattered into the top decile.
CROPLAND_PEAK_NDVI = 0.35


def _season_dates(today: date, start_month: int, end_month: int) -> tuple[date, date]:
    """The most recent complete run of the season's months, as real dates.

    Rabi straddles the new year, so the window has to step back a year rather
    than produce a start later than its end.
    """
    year = today.year
    start = date(year if start_month <= today.month else year - 1, start_month, 1)
    end_year = start.year + (1 if end_month < start_month else 0)
    last_day = 28 if end_month == 2 else 30 if end_month in (4, 6, 9, 11) else 31
    end = date(end_year, end_month, last_day)

    # A window that has not finished yet is fine — we compare what has grown so
    # far — but one entirely in the future is not.
    if start > today:
        start = date(start.year - 1, start_month, 1)
        end = date(end.year - 1, end_month, last_day)
    return start, min(end, today)


def _seasonal_amplitude(ee, geometry, start: date, end: date):
    """Per-pixel NDVI swing across a season: peak minus trough.

    Amplitude, not peak. An orchard or a patch of scrub sits high all year and
    would top a peak-NDVI ranking without growing anything; a sown crop is
    defined by the swing between bare ground and canopy.
    """
    collection = _masked_s2(ee, geometry, start, end).map(
        lambda image: image.normalizedDifference(["B8", "B4"]).rename("ndvi")
    )
    peak = collection.max()
    trough = collection.min()
    return peak.subtract(trough).rename("amplitude"), peak


def _productivity(ee, plot_geometry, centroid, start: date, end: date) -> dict:
    """This plot's amplitude, and the distribution of it around the plot.

    BOTH SIDES COME FROM THE SAME IMAGERY, ON PURPOSE
    -------------------------------------------------
    The plot figure could have been taken from the monthly NDVI series already
    fetched for the history chart. It must not be: monthly means smooth the
    peaks away, so a plot measured that way and a neighbourhood measured from
    individual scenes would differ by the compositing alone. Every field would
    have looked less vigorous than its surroundings, for arithmetic reasons.
    """
    lon, lat = centroid
    neighbourhood = ee.Geometry.Point([lon, lat]).buffer(NEIGHBOURHOOD_RADIUS_M)

    amplitude, peak = _seasonal_amplitude(ee, neighbourhood, start, end)
    cropland = amplitude.updateMask(peak.gte(CROPLAND_PEAK_NDVI))

    reducer = (
        ee.Reducer.percentile([10, 25, 50, 75, 90])
        .combine(reducer2=ee.Reducer.count(), sharedInputs=True)
    )

    stats = cropland.reduceRegion(
        reducer=reducer,
        geometry=neighbourhood,
        scale=NEIGHBOURHOOD_SCALE_M,
        maxPixels=1e9,
        bestEffort=True,
    ).getInfo()

    plot = amplitude.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=plot_geometry,
        scale=SAMPLE_SCALE_M,
        maxPixels=1e9,
        bestEffort=True,
    ).getInfo()

    return {
        "plot_amplitude": plot.get("amplitude"),
        "percentiles": {
            p: stats.get(f"amplitude_p{p}") for p in (10, 25, 50, 75, 90)
        },
        "sample_pixels": int(stats.get("amplitude_count") or 0),
        "neighbourhood_km": NEIGHBOURHOOD_RADIUS_M / 1000,
    }


def _index_bands(ee, image):
    """NDVI, SAVI, NDMI and EVI as one multi-band image."""
    ndvi = image.normalizedDifference(["B8", "B4"]).rename("ndvi")
    ndmi = image.normalizedDifference(["B8", "B11"]).rename("ndmi")

    savi = image.expression(
        "((nir - red) / (nir + red + 0.5)) * 1.5",
        {"nir": image.select("B8"), "red": image.select("B4")},
    ).rename("savi")

    evi = image.expression(
        "2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)",
        {
            "nir": image.select("B8"),
            "red": image.select("B4"),
            "blue": image.select("B2"),
        },
    ).rename("evi")

    return ndvi.addBands([savi, ndmi, evi])


def get_indices(
    place: ResolvedLocation,
    today: date,
    season: str | None = None,
) -> IndicesResult:
    """Current indices plus a 24-month NDVI series for the plot."""
    ee = initialise()
    geometry = _geometry(ee, place)

    recent = _masked_s2(ee, geometry, today - timedelta(days=LOOKBACK_DAYS), today)
    size = recent.size().getInfo()

    if size == 0:
        # Genuinely no usable acquisition. Nulls all the way down - never a
        # plausible-looking substitute.
        return IndicesResult(
            observed_on=None,
            cloud_cover_pct=None,
            indices=tuple(
                IndexValue(
                    key=key,
                    name=str(spec["name"]),
                    value=None,
                    range_min=float(spec["range"][0]),
                    range_max=float(spec["range"][1]),
                    interpretation=interpret(key, None),
                    formula=str(spec["formula"]),
                )
                for key, spec in DEFINITIONS.items()
            ),
            history=(),
            source=f"Copernicus Sentinel-2 — no clear acquisition in {LOOKBACK_DAYS} days",
            tile_url_template=None,
        )

    latest = ee.Image(recent.sort("system:time_start", False).first())
    stats = (
        _index_bands(ee, latest)
        .reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geometry,
            scale=SAMPLE_SCALE_M,
            maxPixels=1e9,
        )
        .getInfo()
    )

    properties = latest.toDictionary(["system:time_start", "CLOUDY_PIXEL_PERCENTAGE"]).getInfo()
    observed_ms = properties.get("system:time_start")
    observed_on = (
        date.fromtimestamp(observed_ms / 1000) if observed_ms else None
    )

    def rounded(key: str) -> float | None:
        value = stats.get(key)
        return round(float(value), 3) if value is not None else None

    indices = tuple(
        IndexValue(
            key=key,
            name=str(spec["name"]),
            value=rounded(key),
            range_min=float(spec["range"][0]),
            range_max=float(spec["range"][1]),
            interpretation=interpret(key, rounded(key)),
            formula=str(spec["formula"]),
        )
        for key, spec in DEFINITIONS.items()
    )

    # One extra reduction, guarded. A failed comparison must cost the farmer
    # the comparison and nothing else — the indices and the history are already
    # computed and useful on their own.
    productivity = None
    try:
        start_month, end_month = _season_window(today, season)
        raw = _productivity(
            ee,
            geometry,
            place.centroid,
            *_season_dates(today, start_month, end_month),
        )
        productivity = ProductivitySample(
            plot_amplitude=raw["plot_amplitude"],
            percentiles=raw["percentiles"],
            sample_pixels=raw["sample_pixels"],
            neighbourhood_km=raw["neighbourhood_km"],
        )
    except BUGS_NOT_OUTAGES:
        raise
    except Exception:
        logger.warning("Productivity comparison failed; omitting it", exc_info=True)

    return IndicesResult(
        observed_on=observed_on,
        cloud_cover_pct=properties.get("CLOUDY_PIXEL_PERCENTAGE"),
        indices=indices,
        history=_ndvi_history(ee, geometry, today),
        productivity=productivity,
        source="Copernicus Sentinel-2 (ESA), cloud-masked, via Google Earth Engine",
        tile_url_template=_tile_url(ee, latest),
    )


def _ndvi_history(ee, geometry, today: date) -> tuple[HistoryPoint, ...]:
    """Monthly mean NDVI for two years, in ONE round trip.

    This is the part that actually informs a sowing decision: it shows what the
    plot has supported season by season, where a single current reading before
    sowing says almost nothing.

    The first version looped in Python and called getInfo() 24 times — about a
    minute of latency against a frontend that allows 10 seconds, so the panel
    failed in the browser while passing in a script. Earth Engine is designed to
    be told the whole computation and asked once: build the monthly composites
    server-side as a FeatureCollection, then fetch the lot in a single call.
    """
    anchor = ee.Date(today.isoformat())

    def monthly(offset):
        offset = ee.Number(offset)
        window_end = anchor.advance(offset.multiply(-30), "day")
        window_start = window_end.advance(-30, "day")

        collection = (
            ee.ImageCollection(S2_COLLECTION)
            .filterBounds(geometry)
            .filterDate(window_start, window_end)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_CLOUD_PCT))
            .map(_mask_clouds_factory(ee))
        )

        # A month with no clear acquisition yields null, not a fabricated value.
        ndvi = ee.Algorithms.If(
            collection.size().gt(0),
            collection.median()
            .normalizedDifference(["B8", "B4"])
            .reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geometry,
                scale=SAMPLE_SCALE_M,
                maxPixels=1e9,
                bestEffort=True,
            )
            .get("nd"),
            None,
        )

        return ee.Feature(
            None, {"date": window_start.format("YYYY-MM-dd"), "ndvi": ndvi}
        )

    months = ee.List.sequence(HISTORY_MONTHS - 1, 0, -1)

    try:
        features = ee.FeatureCollection(months.map(monthly)).getInfo()["features"]
    except Exception:
        logger.warning("NDVI history failed; returning empty series", exc_info=True)
        return ()

    points: list[HistoryPoint] = []
    for feature in features:
        properties = feature.get("properties", {})
        raw = properties.get("ndvi")
        try:
            point_date = date.fromisoformat(properties["date"])
        except (KeyError, ValueError):
            continue
        points.append(
            HistoryPoint(
                date=point_date,
                ndvi=round(float(raw), 3) if raw is not None else None,
            )
        )

    return tuple(points)


def _tile_url(ee, image) -> str | None:
    """XYZ template for an NDVI overlay the map can render directly."""
    try:
        ndvi = image.normalizedDifference(["B8", "B4"])
        map_id = ndvi.getMapId(
            {
                "min": -0.2,
                "max": 0.8,
                # Bare soil through to dense canopy.
                "palette": ["#b8641f", "#d9c48a", "#a8c26a", "#4d8f2f", "#14561a"],
            }
        )
        return map_id["tile_fetcher"].url_format
    except Exception:
        logger.warning("Could not build Sentinel-2 tile URL", exc_info=True)
        return None


def get_conditions(place: ResolvedLocation, season: str | None = None) -> Conditions:
    """Soil from SoilGrids, vegetation from Sentinel-2, weather from reference.

    TODO: when the request carries a drawn polygon, sample that geometry rather
    than a circular buffer around the district centroid. The buffer is a
    reasonable stand-in for a district selection and wrong for a drawn field.
    """
    ee = initialise()
    geometry = _geometry(ee, place)
    radius_m = max(30.0, (place.area_ha * 10_000 / 3.14159) ** 0.5)

    available = 0
    total = 0

    def sample(asset: str, band: str, scale: float = 250) -> float | None:
        """Sample a coarse raster over the plot.

        The geometry is widened to at least one pixel across. A 1 ha field
        buffers to a ~56 m radius, but SoilGrids pixels are 250 m — the region
        falls entirely inside one pixel without containing its centre, and
        reduceRegion returns null. That produced pH=None for every field and a
        completeness of 0.2 while still reporting "reachable".

        bestEffort is belt-and-braces: if the region is somehow still too small
        for the requested scale, Earth Engine coarsens rather than returning
        nothing.
        """
        nonlocal available, total
        total += 1
        try:
            # Widen so at least one pixel centre falls inside.
            coarse_geometry = ee.Geometry.Point(list(place.centroid)).buffer(
                max(radius_m, scale * 1.5)
            )
            value = (
                ee.Image(asset)
                .select(band)
                .reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=coarse_geometry,
                    scale=scale,
                    maxPixels=1e9,
                    bestEffort=True,
                )
                .getInfo()
                .get(band)
            )
            if value is None:
                return None
            available += 1
            return float(value)
        except Exception:
            logger.warning("SoilGrids sample failed: %s/%s", asset, band, exc_info=True)
            return None

    # OpenLandMap scaling, from the catalogue pages:
    #   pH             stored x10      -> divide by 10
    #   organic carbon stored x5, g/kg -> /5 gives g/kg, /10 again gives %
    #   clay, sand     already %
    ph_raw = sample(OLM_PH, "b0")
    soc_raw = sample(OLM_SOC, "b0")
    clay = sample(OLM_CLAY, "b0")
    sand = sample(OLM_SAND, "b0")
    texture_code = sample(OLM_TEXTURE, "b0")

    ndvi: float | None = None
    total += 1
    try:
        recent = _masked_s2(ee, geometry, date.today() - timedelta(days=LOOKBACK_DAYS), date.today())
        if recent.size().getInfo() > 0:
            value = (
                ee.Image(recent.sort("system:time_start", False).first())
                .normalizedDifference(["B8", "B4"])
                .reduceRegion(ee.Reducer.mean(), geometry, SAMPLE_SCALE_M, maxPixels=1e9)
                .getInfo()
                .get("nd")
            )
            if value is not None:
                ndvi = round(float(value), 2)
                available += 1
    except Exception:
        logger.warning("Sentinel-2 NDVI sample failed", exc_info=True)

    # Prefer the published texture class; fall back to inferring from fractions.
    texture = None
    if texture_code is not None:
        texture = USDA_TEXTURE_CLASSES.get(int(round(texture_code)))
    if texture is None:
        texture = _texture_from(clay, sand)

    weather = _sample_climate(ee, place, radius_m, season)
    for value in (weather.annual_rainfall_mm, weather.season_rainfall_mm, weather.avg_temp_c):
        total += 1
        if value is not None:
            available += 1

    return Conditions(
        soil=SoilConditions(
            texture=texture,
            ph=round(ph_raw / 10, 1) if ph_raw is not None else None,
            organic_carbon_pct=round(soc_raw / 50, 2) if soc_raw is not None else None,
            # SoilGrids carries no NPK. The Soil Health Card portal does, but it
            # has no bulk API, so these stay null until that is sourced.
            nitrogen_kg_ha=None,
            phosphorus_kg_ha=None,
            potassium_kg_ha=None,
            source="OpenLandMap 250m (soil), Copernicus Sentinel-2 (vegetation), via Earth Engine",
        ),
        weather=weather,
        ndvi_current=ndvi,
        # Count the fields we KNOW are missing, not just the ones we tried for.
        # NPK has no source yet (SoilGrids and OpenLandMap carry none) and IMD
        # weather is unwired, so reporting 100% beside six dashes on screen was
        # a lie of omission — completeness is meant to answer "how much of what
        # this recommendation needs did we actually have?"
        data_completeness=round(available / (total + UNSOURCED_FIELDS), 2)
        if (total + UNSOURCED_FIELDS)
        else 0.0,
    )


def _sample_climate(
    ee,
    place: ResolvedLocation,
    radius_m: float,
    season: str | None = None,
) -> WeatherConditions:
    """Rainfall and temperature normals for the plot.

    Normals, not current weather: a crop recommendation is about what this place
    is usually like, not what it did last week. Each value fails independently —
    losing temperature should not cost you rainfall.
    """
    lon, lat = place.centroid
    # CHIRPS is 5 km and ERA5-Land 11 km, so sample generously rather than over
    # a field-sized buffer that falls inside a single pixel.
    geometry = ee.Geometry.Point([lon, lat]).buffer(max(radius_m, 6000))

    annual: float | None = None
    seasonal: float | None = None
    temperature: float | None = None

    try:
        chirps = ee.ImageCollection(CHIRPS_DAILY).filterDate(NORMALS_START, NORMALS_END)
        years = 30

        total_mm = (
            chirps.sum()
            .reduceRegion(ee.Reducer.mean(), geometry, 5000, maxPixels=1e9, bestEffort=True)
            .getInfo()
            .get("precipitation")
        )
        if total_mm is not None:
            annual = round(float(total_mm) / years)
    except BUGS_NOT_OUTAGES:
        raise
    except Exception:
        logger.warning("CHIRPS annual rainfall failed", exc_info=True)

    # Hoisted out of the rainfall block: temperature needs the same window, and
    # a rainfall failure must not silently leave temperature unfiltered.
    start_month, end_month = _season_window(date.today(), season)

    try:
        months = (
            ee.Filter.calendarRange(start_month, end_month, "month")
            if start_month <= end_month
            # Rabi straddles the new year, so it is two ranges, not one.
            else ee.Filter.Or(
                ee.Filter.calendarRange(start_month, 12, "month"),
                ee.Filter.calendarRange(1, end_month, "month"),
            )
        )
        season_mm = (
            ee.ImageCollection(CHIRPS_DAILY)
            .filterDate(NORMALS_START, NORMALS_END)
            .filter(months)
            .sum()
            .reduceRegion(ee.Reducer.mean(), geometry, 5000, maxPixels=1e9, bestEffort=True)
            .getInfo()
            .get("precipitation")
        )
        if season_mm is not None:
            seasonal = round(float(season_mm) / 30)
    except BUGS_NOT_OUTAGES:
        raise
    except Exception:
        logger.warning("CHIRPS seasonal rainfall failed", exc_info=True)

    try:
        # Temperature must be filtered to the SAME season as the rainfall.
        #
        # This was an annual mean, which is the wrong number for every crop
        # that does not grow all year. Lucknow averages about 25 C over the
        # year, 29 C in kharif and 18 C in rabi. Feeding 25 C to a rabi
        # ranking scored maize (ideal 21-30 C) at 0.98 and wheat (18-25 C) at
        # 0.85 on the joint-highest-weighted factor — so a summer crop
        # outranked wheat for a winter field. Temperature carries 20% of the
        # score and no input a farmer can buy will fix a wrong one.
        temperature_months = (
            ee.Filter.calendarRange(start_month, end_month, "month")
            if start_month <= end_month
            else ee.Filter.Or(
                ee.Filter.calendarRange(start_month, 12, "month"),
                ee.Filter.calendarRange(1, end_month, "month"),
            )
        )
        kelvin = (
            ee.ImageCollection(ERA5_LAND_MONTHLY)
            .filterDate(NORMALS_START, NORMALS_END)
            .filter(temperature_months)
            .select("temperature_2m")
            .mean()
            .reduceRegion(ee.Reducer.mean(), geometry, 11000, maxPixels=1e9, bestEffort=True)
            .getInfo()
            .get("temperature_2m")
        )
        if kelvin is not None:
            temperature = round(float(kelvin) - 273.15, 1)
    except BUGS_NOT_OUTAGES:
        raise
    except Exception:
        logger.warning("ERA5-Land temperature failed", exc_info=True)

    return WeatherConditions(
        annual_rainfall_mm=annual,
        season_rainfall_mm=seasonal,
        avg_temp_c=temperature,
        source=(
            "CHIRPS 1994-2023 rainfall normals and ERA5-Land temperature, "
            "both for this crop season, via Earth Engine"
        ),
    )


def _texture_from(clay: float | None, sand: float | None) -> str | None:
    """Coarse USDA texture class from clay and sand percentages.

    Only used when the published texture class is unavailable. OpenLandMap
    stores these already as percentages.
    """
    if clay is None or sand is None:
        return None
    clay_pct = clay
    sand_pct = sand

    if clay_pct >= 40:
        return "clay"
    if clay_pct >= 27:
        return "clay loam"
    if sand_pct >= 70:
        return "sandy loam"
    if sand_pct >= 52:
        return "loam"
    return "silt loam"
