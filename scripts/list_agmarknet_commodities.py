#!/usr/bin/env python3
"""Dump the distinct commodity names currently in the Agmarknet feed.

Run this to check COMMODITY_NAMES against reality instead of against
documentation. A crop whose alias does not match anything in the feed falls
back to MSP silently — nothing errors, the price is just never live.

    python scripts/list_agmarknet_commodities.py
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

import httpx

from apps.api.services.agmarknet import (
    BASE_URL,
    BROWSER_HEADERS,
    COMMODITY_NAMES,
    _normalise_commodity,
    _first,
)


def main() -> int:
    api_key = os.getenv("DATA_GOV_IN_API_KEY") or os.getenv("MARKET_PRICE_API_KEY")
    if not api_key:
        print("No API key. Set DATA_GOV_IN_API_KEY in .env")
        return 1

    print("Fetching the feed…")
    with httpx.Client(timeout=60.0, headers=BROWSER_HEADERS, follow_redirects=True) as http:
        response = http.get(
            BASE_URL, params={"api-key": api_key, "format": "json", "limit": "10000"}
        )
        response.raise_for_status()
        records = response.json().get("records", [])

    counts = Counter(
        (_first(r, "commodity", "Commodity") or "").strip() for r in records
    )
    print(f"{len(records)} records, {len(counts)} distinct commodities\n")

    # Which of ours actually match something?
    mapped: dict[str, str] = {}
    for code, aliases in COMMODITY_NAMES.items():
        wanted = {_normalise_commodity(a) for a in aliases}
        hits = [name for name in counts if _normalise_commodity(name) in wanted]
        mapped[code] = ", ".join(hits) if hits else ""

    print("OUR CROPS:")
    for code, hits in sorted(mapped.items()):
        status = "OK  " if hits else "MISS"
        print(f"  {status} {code:10} -> {hits or '(nothing in the feed matched)'}")

    missing = [code for code, hits in mapped.items() if not hits]
    if missing:
        print(f"\n{len(missing)} crop(s) matched nothing. Either they are not trading")
        print("today, or the alias is wrong. Check against the list below.\n")

    print("TOP 60 COMMODITY NAMES IN THE FEED (name x record count):")
    for name, count in counts.most_common(60):
        print(f"  {count:5}  {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
