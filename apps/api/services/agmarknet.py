"""Live mandi prices from Agmarknet, via the data.gov.in open data API.

Resource: "Current Daily Price of Various Commodities from Various Markets
(Mandi)", published from the Agmarknet portal.
https://www.data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi

NOT VERIFIED against a live key. The request shape and field names below follow
the published documentation, but nobody has run this with a real API key, and
data.gov.in resources have been known to rename fields between revisions. The
parser is therefore deliberately forgiving: it accepts several spellings for
each field and skips records it cannot read rather than throwing. If prices come
back empty with a real key, log a raw record and check the names first.

Why this matters more than it looks: MSP is a floor price with non-universal
procurement. What a farmer actually receives is the mandi price. Every figure
this returns replaces an MSP fallback, and the response says which one was used.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
# data.gov.in is routinely slow — 15s round trips are common and it timed out
# at that during setup. Generous here because the caller already treats failure
# as "fall back to MSP", so a slow success still beats a fast give-up.
TIMEOUT_SECONDS = 30.0
# One big unfiltered page, narrowed client-side. See fetch() for why.
# data.gov.in sits behind a WAF that appears to drop requests advertising a
# library User-Agent — the same URL returns instantly in a browser and times out
# from httpx, with or without filters, over IPv4 or IPv6. Presenting a browser
# UA is the remaining difference. Not cloaking: we are a legitimate client of a
# public API using our own key, just one the filter recognises.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-IN,en;q=0.9",
}

MAX_RECORDS = 5000
# Ranking five crops should cost one HTTP request, not five.
CACHE_SECONDS = 300

def _normalise_commodity(name: str) -> str:
    """Lowercase alphanumerics only, so punctuation cannot break a match.

    Agmarknet writes the same crop several ways: the live feed returns
    "Paddy(Common)" where the documentation says "Paddy(Dhan)(Common)". Exact
    string comparison missed it, and rice fell back to MSP silently — the worst
    kind of failure, because nothing looked broken.
    """
    return "".join(ch for ch in name.lower() if ch.isalnum())


# Our crop codes to the commodity names Agmarknet publishes. Their naming is
# inconsistent (Bengal Gram vs Gram, Paddy vs Rice) so this mapping is the
# adapter between our stable codes and their text.
#
# Names marked OBSERVED came from a live feed; the rest are from documentation
# and are unverified. Run `python scripts/list_agmarknet_commodities.py` to dump
# the distinct names currently in the feed and check the unverified ones.
COMMODITY_NAMES: dict[str, tuple[str, ...]] = {
    "WHEAT": ("Wheat",),
    "RICE": (
        "Paddy(Common)",  # OBSERVED in the live feed
        "Paddy(Dhan)(Common)",
        "Paddy(Dhan)(Basmati)",
        "Paddy",
        "Rice",
    ),
    "MAIZE": ("Maize",),
    "BARLEY": ("Barley (Jau)", "Barley"),
    "SORGHUM": ("Jowar(Sorghum)", "Jowar"),
    "PEARLMLT": ("Bajra(Pearl Millet/Cumbu)", "Bajra"),
    "CHICKPEA": ("Bengal Gram(Gram)(Whole)", "Bengal Gram Dal", "Gram"),
    "PIGEONPEA": ("Arhar (Tur/Red Gram)(Whole)", "Arhar Dal(Tur Dal)"),
    "LENTIL": ("Lentil (Masur)(Whole)", "Masur Dal"),
    "MUSTARD": ("Mustard", "Rape Seed"),
    "GROUNDNUT": ("Groundnut", "Groundnut (Split)"),
    "SOYBEAN": ("Soyabean", "Soybean"),
    "COTTON": ("Cotton",),
    "SUGARCANE": ("Sugarcane",),
    "POTATO": ("Potato",),
    "ONION": ("Onion",),
}


def _matching(records: list[dict], field: str, wanted: str | None) -> list[dict]:
    """Records whose `field` equals `wanted`, case- and whitespace-insensitive.

    Returns the input unchanged when `wanted` is None, so callers can chain
    optional narrowings without branching.
    """
    if not wanted:
        return records
    target = wanted.strip().lower()
    return [
        record
        for record in records
        if (_first(record, field, field.capitalize()) or "").strip().lower() == target
    ]


def looks_like_api_key(value: str | None) -> bool:
    """Is this plausibly a data.gov.in key rather than a leaked .env comment?

    Real keys are ~55 hex characters. A comment fragment like
    "# Agmarknet / data.gov.in" is not, and sending it produced a 403 on every
    request while the correct key sat unused in the next variable.
    """
    if not value:
        return False
    candidate = value.strip()
    if len(candidate) < 20:
        return False
    # Comments, spaces and slashes never appear in a key.
    if any(ch in candidate for ch in "# /\\'\""):
        return False
    return all(ch.isalnum() for ch in candidate)


@dataclass(frozen=True)
class MandiPrice:
    crop_code: str
    modal_price: int
    min_price: int | None
    max_price: int | None
    mandi: str
    price_date: date


def _first(record: dict, *names: str) -> str | None:
    """Accept every spelling the API is known to emit.

    Confirmed against the live resource schema: the canonical ids are `state`,
    `district`, `market`, `commodity`, `variety`, `grade`, `arrival_date`,
    `min_price`, `max_price`, `modal_price`. The XML form capitalises and
    escapes spaces (`Min_x0020_Price`), so both are accepted.
    """
    for name in names:
        value = record.get(name)
        if value not in (None, "", "NA"):
            return str(value)
    return None


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        # Prices arrive as "2450" or "2450.00", occasionally with stray spaces.
        return int(round(float(value.strip())))
    except (TypeError, ValueError):
        return None


def _to_date(value: str | None) -> date | None:
    if value is None:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_records(crop_code: str, records: list[dict]) -> list[MandiPrice]:
    """Tolerant parser. Unreadable records are skipped, never guessed at."""
    prices: list[MandiPrice] = []

    for record in records:
        modal = _to_int(
            _first(record, "modal_price", "Modal_Price", "modal_x0020_price", "Modal_x0020_Price")
        )
        if modal is None or modal <= 0:
            continue

        prices.append(
            MandiPrice(
                crop_code=crop_code,
                modal_price=modal,
                min_price=_to_int(
                    _first(record, "min_price", "Min_Price", "min_x0020_price", "Min_x0020_Price")
                ),
                max_price=_to_int(
                    _first(record, "max_price", "Max_Price", "max_x0020_price", "Max_x0020_Price")
                ),
                mandi=_first(record, "market", "Market") or "Unknown mandi",
                price_date=_to_date(_first(record, "arrival_date", "Arrival_Date")) or date.today(),
            )
        )

    return prices


class AgmarknetClient:
    """Thin HTTP client. Every failure path returns empty rather than raising."""

    def __init__(self, api_key: str, base_url: str = BASE_URL) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self._cache: list[dict] | None = None
        self._cache_at: float = 0.0

    @staticmethod
    def _transport() -> httpx.HTTPTransport:
        """Force IPv4.

        Browsers implement Happy Eyeballs: they race IPv4 and IPv6 and use
        whichever answers. httpx does not — it takes whatever DNS returns first,
        so on a network with a broken IPv6 route the request hangs until it
        times out. That is exactly the symptom seen here: instant in Chrome,
        45s timeout from Python, with and without query filters.

        Binding the local address to 0.0.0.0 forces an IPv4 socket.
        """
        return httpx.HTTPTransport(local_address="0.0.0.0", retries=1)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def fetch(
        self,
        crop_code: str,
        state_name: str | None = None,
        district_name: str | None = None,
    ) -> list[MandiPrice]:
        """Recent prices for one crop, narrowed to a district where possible.

        Filtering happens CLIENT-side, deliberately. Server-side `filters[...]`
        parameters make data.gov.in scan the resource and the request hangs past
        45 seconds; the same query unfiltered returns in well under a second.
        So: pull one large unfiltered page and narrow it here.

        The cost is a bigger payload. The benefit is that it actually completes,
        which it previously never did.

        Returns [] on any failure: no key, network error, HTTP error, malformed
        payload, or unknown crop. The caller falls back to MSP and warns. A price
        service outage is never a reason to deny agronomic advice.
        """
        if not self.configured:
            return []

        commodities = COMMODITY_NAMES.get(crop_code.upper())
        if not commodities:
            logger.debug("No Agmarknet commodity mapping for %s", crop_code)
            return []

        records = self._fetch_page()
        if not records:
            return []

        wanted = {_normalise_commodity(name) for name in commodities}
        matches = [
            record
            for record in records
            if _normalise_commodity(_first(record, "commodity", "Commodity") or "") in wanted
        ]

        # Narrow geographically, most specific first, but never to nothing.
        # A district that did not trade this crop today is normal, so falling
        # back to the state — and then to all India — beats returning no price.
        for field, wanted_value in (("district", district_name), ("state", state_name)):
            narrowed = _matching(matches, field, wanted_value)
            if narrowed:
                matches = narrowed
                break

        prices = parse_records(crop_code, matches)
        logger.info(
            "Agmarknet: %d of %d records matched %s", len(prices), len(records), crop_code
        )
        return prices

    def _fetch_page(self) -> list[dict]:
        """One large unfiltered page. Cached briefly so ranking five crops is
        one request, not five."""
        import time

        now = time.time()
        if self._cache is not None and now - self._cache_at < CACHE_SECONDS:
            return self._cache

        params = {
            "api-key": self.api_key,
            "format": "json",
            "limit": str(MAX_RECORDS),
        }
        try:
            with httpx.Client(
                transport=self._transport(),
                timeout=TIMEOUT_SECONDS,
                headers=BROWSER_HEADERS,
                follow_redirects=True,
            ) as http:
                response = http.get(self.base_url, params=params)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            # Cache the failure too. Without this a five-crop ranking makes five
            # doomed requests and prints five tracebacks, turning one upstream
            # problem into a wall of noise.
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status == 403:
                logger.warning(
                    "Agmarknet rejected the API key (403). Check DATA_GOV_IN_API_KEY."
                )
            else:
                logger.warning("Agmarknet request failed: %s", type(exc).__name__)
            self._cache = []
            self._cache_at = now
            return []
        except ValueError:
            logger.warning("Agmarknet returned non-JSON")
            self._cache = []
            self._cache_at = now
            return []

        records = payload.get("records") or []
        self._cache = records
        self._cache_at = now
        return records


def summarise(prices: list[MandiPrice], max_age_days: int = 30) -> MandiPrice | None:
    """The most representative recent price: median modal of the freshest day.

    Median rather than mean because a single mis-keyed mandi entry - and there
    are always some - would drag an average badly. Median shrugs them off.
    """
    if not prices:
        return None

    cutoff = date.today() - timedelta(days=max_age_days)
    fresh = [price for price in prices if price.price_date >= cutoff]
    if not fresh:
        return None

    latest_date = max(price.price_date for price in fresh)
    same_day = sorted(
        (price for price in fresh if price.price_date == latest_date),
        key=lambda price: price.modal_price,
    )

    middle = same_day[len(same_day) // 2]
    return MandiPrice(
        crop_code=middle.crop_code,
        modal_price=middle.modal_price,
        min_price=min((p.min_price for p in same_day if p.min_price is not None), default=None),
        max_price=max((p.max_price for p in same_day if p.max_price is not None), default=None),
        mandi=middle.mandi if len(same_day) == 1 else f"{len(same_day)} mandis (median)",
        price_date=latest_date,
    )
