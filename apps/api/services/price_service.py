"""Market prices.

Order of preference:
  1. Live Agmarknet mandi prices for the district (not yet implemented).
  2. The notified support price from data/reference/economics.yaml.
  3. Nothing - and the economics come back null with a warning attached.

MSP is a floor with non-universal procurement, not what the farmer will be paid.
Whenever the fallback is used the response says so in `price_source`, so the
farmer knows which of the two they are looking at.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from apps.api.core.config import get_settings
from apps.api.core.reference import ReferenceData
from apps.api.services.agmarknet import AgmarknetClient, looks_like_api_key, summarise
from services.ml.types import CropSpec

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Price:
    per_quintal: int | None
    source: str | None
    as_of: date | None
    is_live: bool


class PriceService:
    """Wraps price lookup so the orchestrator does not care where it came from."""

    def __init__(
        self,
        reference: ReferenceData,
        client: AgmarknetClient | None = None,
        history=None,
    ) -> None:
        self.reference = reference
        self.history = history
        settings = get_settings()
        # Take the first value that actually looks like a key. Preferring
        # whichever is merely non-empty meant a leaked .env comment in
        # MARKET_PRICE_API_KEY shadowed the real key and 403'd every request.
        candidates = {
            "DATA_GOV_IN_API_KEY": settings.data_gov_in_api_key,
            "MARKET_PRICE_API_KEY": settings.market_price_api_key,
        }
        chosen = ""
        for name, value in candidates.items():
            if looks_like_api_key(value):
                chosen = value
                break
            if value:
                logger.warning(
                    "%s is set but does not look like an API key (%d chars) — "
                    "is a .env comment leaking into the value? Ignoring it.",
                    name,
                    len(value.strip()),
                )
        self.client = client or AgmarknetClient(chosen)

    def for_crop(self, crop: CropSpec, district_code: str) -> Price:
        live = self._live_price(crop, district_code)
        if live is not None:
            return live

        if crop.price_per_quintal is None:
            return Price(per_quintal=None, source=None, as_of=None, is_live=False)

        econ = self.reference.economics_raw.get(crop.crop_code, {})
        source = self.reference.source_for(econ.get("price_source"))
        return Price(
            per_quintal=crop.price_per_quintal,
            source=source.citation if source else "Notified support price",
            as_of=None,
            is_live=False,
        )

    def _live_price(self, crop: CropSpec, district_code: str) -> Price | None:
        """Agmarknet lookup. Fails soft: any problem returns None and MSP wins.

        A price service outage is not a reason to deny a farmer agronomic
        advice, so nothing here is allowed to raise.
        """
        if not self.client.configured:
            return None

        district = self._district_name(district_code)
        state = self._state_name(district_code)

        try:
            prices = self.client.fetch(crop.crop_code, state_name=state, district_name=district)
            # Nothing in this district is normal - not every mandi trades every
            # crop every day. Widen to the state before giving up.
            if not prices and state:
                prices = self.client.fetch(crop.crop_code, state_name=state)
        except Exception:
            logger.exception("Agmarknet lookup failed for %s", crop.crop_code)
            return None

        best = summarise(prices)
        if best is None:
            return None

        # Keep every observation. data.gov.in has no historical endpoint, so
        # this accumulator is the only route to a real seasonal picture.
        if self.history is not None:
            for price in prices:
                self.history.record(
                    crop_code=crop.crop_code,
                    district_code=district_code,
                    mandi=price.mandi,
                    price_date=price.price_date,
                    modal_price=price.modal_price,
                )

        return Price(
            per_quintal=best.modal_price,
            source=f"Agmarknet, {best.mandi}, {best.price_date.isoformat()}",
            as_of=best.price_date,
            is_live=True,
        )

    def _district_name(self, district_code: str) -> str | None:
        for state in self.reference.districts["states"]:
            for district in state["districts"]:
                if district["district_code"] == district_code:
                    return district["district_name"]
        return None

    def _state_name(self, district_code: str) -> str | None:
        for state in self.reference.districts["states"]:
            for district in state["districts"]:
                if district["district_code"] == district_code:
                    return state["state_name"]
        return None
