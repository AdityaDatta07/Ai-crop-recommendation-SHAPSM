#!/usr/bin/env python3
"""Diagnose the Earth Engine and Agmarknet connections.

Run this after putting your credentials in .env. It exercises every remote call
the app makes and prints a report you can paste back into a chat WITHOUT
leaking anything: keys are never printed, only whether they are present and
whether they work.

    python scripts/verify_external_sources.py

What it deliberately DOES print: the raw field names Agmarknet returns. Those
are not secret, and they are the one thing needed to confirm the parser reads
the right keys — data.gov.in has renamed them between revisions.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Load .env the same way the app does.
try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass


def redact(value: str | None) -> str:
    """Enough to confirm the right key is loaded, useless to anyone else."""
    if not value:
        return "NOT SET"
    return f"set ({len(value)} chars, ends …{value[-4:]})"


def rule(title: str) -> None:
    print(f"\n{'=' * 62}\n{title}\n{'=' * 62}")


def check_config() -> dict:
    rule("1. Configuration")
    config = {
        "GEE_PROJECT_ID": os.getenv("GEE_PROJECT_ID", ""),
        "GEE_PRIVATE_KEY_PATH": os.getenv("GEE_PRIVATE_KEY_PATH", ""),
        "GEE_SERVICE_ACCOUNT_KEY_B64": os.getenv("GEE_SERVICE_ACCOUNT_KEY_B64", ""),
        "DATA_GOV_IN_API_KEY": os.getenv("DATA_GOV_IN_API_KEY", ""),
        "MARKET_PRICE_API_KEY": os.getenv("MARKET_PRICE_API_KEY", ""),
        "USE_MOCK_GEO": os.getenv("USE_MOCK_GEO", "true"),
    }

    # The project id is not sensitive and is useful in a report.
    print(f"  GEE_PROJECT_ID              : {config['GEE_PROJECT_ID'] or 'NOT SET'}")
    print(f"  GEE_PRIVATE_KEY_PATH        : {config['GEE_PRIVATE_KEY_PATH'] or 'NOT SET'}")
    print(f"  GEE_SERVICE_ACCOUNT_KEY_B64 : {redact(config['GEE_SERVICE_ACCOUNT_KEY_B64'])}")
    print(f"  DATA_GOV_IN_API_KEY         : {redact(config['DATA_GOV_IN_API_KEY'])}")
    print(f"  MARKET_PRICE_API_KEY        : {redact(config['MARKET_PRICE_API_KEY'])}")
    print(f"  USE_MOCK_GEO                : {config['USE_MOCK_GEO']}")

    key_path = config["GEE_PRIVATE_KEY_PATH"]
    if key_path:
        path = Path(key_path)
        if not path.is_absolute():
            path = REPO_ROOT / key_path
        if path.exists():
            try:
                with path.open(encoding="utf-8") as handle:
                    key = json.load(handle)
                print(f"  key file                    : found, type={key.get('type')}")
                print(f"  service account email       : {key.get('client_email', 'MISSING')}")
            except Exception as exc:
                print(f"  key file                    : UNREADABLE — {exc}")
        else:
            print(f"  key file                    : NOT FOUND at {path}")

    return config


def check_earth_engine() -> None:
    rule("2. Earth Engine")

    try:
        import ee  # noqa: F401
    except ImportError:
        print("  FAIL  earthengine-api not installed.")
        print("        pip install --only-binary=:all: -r apps/api/requirements.txt")
        return

    from services.geo.earthengine import EarthEngineNotConfigured, initialise

    try:
        ee_module = initialise()
        print("  OK    authenticated")
    except EarthEngineNotConfigured as exc:
        print(f"  FAIL  not configured — {exc}")
        return
    except Exception as exc:
        print(f"  FAIL  authentication failed — {type(exc).__name__}: {exc}")
        print("        Common causes: project not registered at")
        print("        code.earthengine.google.com/register, or the service account")
        print("        lacks the 'Earth Engine Resource Viewer' role.")
        traceback.print_exc(limit=2)
        return

    # A point in Lucknow district, which the reference data covers.
    lon, lat = 80.94, 26.84
    point = ee_module.Geometry.Point([lon, lat]).buffer(100)

    try:
        collection = (
            ee_module.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(point)
            .filterDate("2026-06-01", str(date.today()))
        )
        size = collection.size().getInfo()
        print(f"  OK    Sentinel-2 reachable — {size} scenes since June near Lucknow")
    except Exception as exc:
        print(f"  FAIL  Sentinel-2 query failed — {type(exc).__name__}: {exc}")
        return

    # Soil rasters are 250 m; sample over at least that or reduceRegion returns
    # null. Each asset is probed separately so a bad id is named individually.
    wide = ee_module.Geometry.Point([lon, lat]).buffer(400)
    from services.geo.earthengine import OLM_CLAY, OLM_PH, OLM_SAND, OLM_SOC, OLM_TEXTURE

    for label, asset, band, scale_note in (
        ("pH", OLM_PH, "b0", "/10 = pH"),
        ("organic carbon", OLM_SOC, "b0", "/50 = %"),
        ("clay %", OLM_CLAY, "b0", "as-is"),
        ("sand %", OLM_SAND, "b0", "as-is"),
        ("texture class", OLM_TEXTURE, "b0", "USDA code 1-12"),
    ):
        try:
            value = (
                ee_module.Image(asset)
                .select(band)
                .reduceRegion(
                    ee_module.Reducer.mean(), wide, 250, maxPixels=1e9, bestEffort=True
                )
                .getInfo()
                .get(band)
            )
            if value is None:
                print(f"  FAIL  {label:15} null — check asset id: {asset}")
            else:
                print(f"  OK    {label:15} raw={value} ({scale_note})")
        except Exception as exc:
            print(f"  FAIL  {label:15} {type(exc).__name__}: {exc}")

    # Climate: CHIRPS rainfall normals and ERA5-Land temperature.
    try:
        from services.geo.earthengine import _sample_climate
        from services.geo.types import ResolvedLocation

        climate = _sample_climate(
            ee_module, ResolvedLocation("UP", "UP-LKO", "Lucknow", (lon, lat), 1.0), 60.0
        )
        print(
            f"  {'OK  ' if climate.annual_rainfall_mm else 'FAIL'} annual rainfall  "
            f"{climate.annual_rainfall_mm} mm/yr"
        )
        print(
            f"  {'OK  ' if climate.season_rainfall_mm else 'FAIL'} season rainfall  "
            f"{climate.season_rainfall_mm} mm"
        )
        print(
            f"  {'OK  ' if climate.avg_temp_c else 'FAIL'} temperature      "
            f"{climate.avg_temp_c} C"
        )
    except Exception as exc:
        print(f"  FAIL  climate sampling — {type(exc).__name__}: {exc}")

    # The full path the app actually uses.
    try:
        from services.geo.earthengine import get_conditions, get_indices
        from services.geo.types import ResolvedLocation

        place = ResolvedLocation("UP", "UP-LKO", "Lucknow", (lon, lat), 1.0)

        conditions = get_conditions(place)
        print(
            f"  OK    get_conditions — pH={conditions.soil.ph} "
            f"texture={conditions.soil.texture} ndvi={conditions.ndvi_current} "
            f"completeness={conditions.data_completeness}"
        )

        print("        get_indices — this makes 24 history calls, allow a minute…")
        indices = get_indices(place, date.today())
        print(f"  OK    observed_on={indices.observed_on} cloud={indices.cloud_cover_pct}%")
        for index in indices.indices:
            print(f"          {index.key:5} = {index.value}")
        usable = [p for p in indices.history if p.ndvi is not None]
        print(f"        history: {len(usable)}/{len(indices.history)} months with data")
        print(f"        tile overlay: {'YES' if indices.tile_url_template else 'NO'}")
    except Exception as exc:
        print(f"  FAIL  full path failed — {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=3)


def check_agmarknet(config: dict) -> None:
    rule("3. Agmarknet (data.gov.in)")

    api_key = config["DATA_GOV_IN_API_KEY"] or config["MARKET_PRICE_API_KEY"]
    if not api_key:
        print("  SKIP  no API key set")
        return

    import httpx

    from apps.api.services.agmarknet import BASE_URL, AgmarknetClient, parse_records, summarise

    # Raw call first: this is what confirms the field names.
    # Two theories have already been wrong (server-side filters, IPv6). So test
    # the whole matrix in one run rather than one guess per round trip.
    import time as _time

    from apps.api.services.agmarknet import BROWSER_HEADERS

    params = {"api-key": api_key, "format": "json", "limit": "1"}
    ipv4 = httpx.HTTPTransport(local_address="0.0.0.0")

    print("  probe matrix (headers x transport):")
    for label, headers, transport in (
        ("library UA, default", None, None),
        ("library UA, IPv4", None, ipv4),
        ("browser UA, default", BROWSER_HEADERS, None),
        ("browser UA, IPv4", BROWSER_HEADERS, httpx.HTTPTransport(local_address="0.0.0.0")),
    ):
        start = _time.time()
        try:
            with httpx.Client(
                transport=transport, timeout=20.0, headers=headers, follow_redirects=True
            ) as probe:
                r = probe.get(BASE_URL, params=params)
            print(f"    {label:22} HTTP {r.status_code} in {_time.time() - start:4.1f}s")
        except Exception as exc:
            print(
                f"    {label:22} FAILED after {_time.time() - start:4.1f}s"
                f" — {type(exc).__name__}"
            )

    # Does the OS-level client work where Python does not? If curl succeeds,
    # the problem is inside Python's stack, not the network.
    print("\n  same request via curl (OS networking, not Python):")
    import shutil
    import subprocess

    if shutil.which("curl"):
        start = _time.time()
        result = subprocess.run(
            ["curl", "-s", "-o", os.devnull, "-w", "%{http_code}", "--max-time", "25",
             f"{BASE_URL}?api-key={api_key}&format=json&limit=1"],
            capture_output=True, text=True,
        )
        code = (result.stdout or "").strip() or "no response"
        print(f"    curl HTTP {code} in {_time.time() - start:4.1f}s")
    else:
        print("    curl not on PATH, skipped")

    # Browser headers, same as the client. Without them the WAF drops the
    # request and it read-times-out rather than returning an error.
    payload = None
    try:
        with httpx.Client(
            timeout=45.0, headers=BROWSER_HEADERS, follow_redirects=True
        ) as http:
            response = http.get(
                BASE_URL, params={"api-key": api_key, "format": "json", "limit": "3"}
            )
        print(f"  HTTP  {response.status_code}")
        if response.status_code == 403:
            print("  FAIL  403 — the API key was rejected. Check it is the full")
            print("        55-character key from data.gov.in/user/myaccount.")
            return
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"  FAIL  request failed — {type(exc).__name__}: {exc}")
        print("        Survivable: the app falls back to MSP prices.")
        return

    records = payload.get("records") or []
    print(f"  OK    {payload.get('total', '?')} total records available, {len(records)} fetched")

    if not records:
        print("  WARN  no records returned; cannot verify field names")
        return

    # THIS is the bit to paste back. Field names are not secret.
    print("\n  >>> RAW FIELD NAMES — paste this section back <<<")
    print(f"  keys: {sorted(records[0].keys())}")
    print("  first record:")
    for key, value in sorted(records[0].items()):
        print(f"    {key:24} = {value!r}")

    parsed = parse_records("WHEAT", records)
    print(f"\n  parser read {len(parsed)}/{len(records)} records")
    if len(parsed) < len(records):
        print("  WARN  the parser is missing fields — the key list above shows why")

    # Demonstrate WHY the client filters locally: time both shapes.
    import time

    print("\n  timing (this is why filtering moved client-side):")
    start = time.time()
    try:
        httpx.get(
            BASE_URL,
            params={"api-key": api_key, "format": "json", "limit": "10"},
            timeout=45.0,
        )
        print(f"    unfiltered      : {time.time() - start:5.1f}s")
    except Exception as exc:
        print(f"    unfiltered      : FAILED {type(exc).__name__}")

    start = time.time()
    try:
        httpx.get(
            BASE_URL,
            params={
                "api-key": api_key, "format": "json", "limit": "10",
                "filters[commodity]": "Wheat",
            },
            timeout=45.0,
        )
        print(f"    server-filtered : {time.time() - start:5.1f}s")
    except Exception as exc:
        print(f"    server-filtered : FAILED {type(exc).__name__} — as expected")

    # Now the real client path for a crop that trades widely.
    client = AgmarknetClient(api_key)
    for crop, state in (("WHEAT", "Uttar Pradesh"), ("ONION", "Maharashtra")):
        try:
            prices = client.fetch(crop, state_name=state)
            best = summarise(prices)
            if best:
                print(
                    f"  OK    {crop} in {state}: Rs {best.modal_price}/quintal "
                    f"({best.mandi}, {best.price_date})"
                )
            else:
                print(f"  WARN  {crop} in {state}: {len(prices)} records but none usable/recent")
        except Exception as exc:
            print(f"  FAIL  {crop} — {type(exc).__name__}: {exc}")


def main() -> int:
    print("External data source diagnostics")
    print("Keys are never printed. Safe to share this output.")
    config = check_config()
    check_earth_engine()
    check_agmarknet(config)
    rule("Done")
    print("Paste the whole output back. The Agmarknet field-name block is the")
    print("part that lets the parser be corrected if it is reading wrong keys.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
