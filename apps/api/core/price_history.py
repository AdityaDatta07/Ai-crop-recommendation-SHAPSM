"""Records every mandi price we observe, so a forecast becomes possible.

data.gov.in serves only a current snapshot — there is no historical endpoint.
The only route to a real seasonal picture is to keep what we see. This starts
empty and deepens every time the API is used, which means the harvest-month
outlook gets better on its own rather than needing a data source that does not
exist.

Shares the SQLite file with the results store; the table mirrors market_prices
in db/schema.sql so the Supabase path can use identical queries later.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Two years is enough to see the same harvest month twice.
RETENTION_DAYS = 730


class PriceHistory:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS market_prices (
                    crop_code     TEXT NOT NULL,
                    district_code TEXT,
                    mandi         TEXT,
                    price_date    TEXT NOT NULL,
                    modal_price   INTEGER NOT NULL,
                    recorded_at   TEXT NOT NULL,
                    PRIMARY KEY (crop_code, district_code, mandi, price_date)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS market_prices_lookup "
                "ON market_prices (crop_code, price_date)"
            )

    def record(
        self,
        crop_code: str,
        district_code: str | None,
        mandi: str,
        price_date: date,
        modal_price: int,
    ) -> None:
        """Idempotent: re-observing the same day replaces rather than duplicates."""
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT OR REPLACE INTO market_prices "
                    "(crop_code, district_code, mandi, price_date, modal_price, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        crop_code,
                        district_code,
                        mandi,
                        price_date.isoformat(),
                        modal_price,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
        except sqlite3.Error:
            # Recording history must never cost the farmer their answer.
            logger.warning("Could not record price for %s", crop_code, exc_info=True)

    def prices_in_month(self, crop_code: str, month: int) -> list[int]:
        """Every price seen for this crop in this calendar month, any year.

        Month rather than month-and-year on purpose: the question is what this
        crop fetches at harvest time, and two Aprils are more informative than
        one.
        """
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT modal_price FROM market_prices "
                    "WHERE crop_code = ? AND CAST(strftime('%m', price_date) AS INTEGER) = ?",
                    (crop_code, month),
                ).fetchall()
            return [int(row["modal_price"]) for row in rows]
        except sqlite3.Error:
            logger.warning("Could not read price history for %s", crop_code, exc_info=True)
            return []

    def harvest_month_comparison(
        self, crop_code: str, month: int, district_code: str | None = None
    ) -> tuple[list[int], list[int], str]:
        """Prices in the harvest month, prices in every other month, and scope.

        Returns `(harvest_month_prices, other_month_prices, scope)` where scope
        is "district", "national" or "none".

        WHY THE FALLBACK IS REPORTED AND NOT SILENT
        -------------------------------------------
        A district's own mandi record is the right comparison, but most
        districts will have almost none of it for a long time. Falling back to
        every district is genuinely more useful than showing nothing — a
        nationwide harvest-month dip in onion is real information about onion.

        It is also a different claim. Rendering the two identically would let a
        farmer in Nashik read a national average as their local market, which
        is exactly the substitution `precision` exists to prevent on the
        location side. So the scope comes back with the numbers and the UI
        says which one it is.

        BOTH SIDES COME FROM THE SAME SCOPE
        -----------------------------------
        District harvest prices against national rest-of-year prices would
        compare two different populations and call the difference seasonality.
        If we fall back, we fall back for both.

        A REFUSAL STILL REPORTS WHAT WE HOLD
        ------------------------------------
        This used to return `[], [], "none"` whenever it could not make the
        comparison, which threw away counts it had just measured. The screen
        then read "we have 0 recorded prices from the harvest month and 0 from
        the rest of the year" for a crop with 360 observations from the rest of
        the year — a false statement, generated by a correct refusal.

        So the wider set comes back even when unusable. The caller decides
        what to say; it can only say it truthfully if it is told.
        """
        district_harvest = self._prices(crop_code, month, True, district_code)
        district_other = self._prices(crop_code, month, False, district_code)

        if district_code and district_harvest and district_other:
            return district_harvest, district_other, "district"

        national_harvest = self._prices(crop_code, month, True, None)
        national_other = self._prices(crop_code, month, False, None)
        if national_harvest and national_other:
            return national_harvest, national_other, "national"

        # Unusable, but not nothing. Scope is "none" so no caller mistakes
        # these for a comparison, while the counts stay honest.
        return national_harvest, national_other, "none"

    def _prices(
        self, crop_code: str, month: int, in_month: bool, district_code: str | None
    ) -> list[int]:
        comparison = "=" if in_month else "!="
        sql = (
            "SELECT modal_price FROM market_prices "
            f"WHERE crop_code = ? AND CAST(strftime('%m', price_date) AS INTEGER) {comparison} ?"
        )
        params: list[object] = [crop_code, month]
        if district_code:
            sql += " AND district_code = ?"
            params.append(district_code)
        try:
            with self._connect() as connection:
                rows = connection.execute(sql, params).fetchall()
            return [int(row["modal_price"]) for row in rows]
        except sqlite3.Error:
            logger.warning("Could not read price history for %s", crop_code, exc_info=True)
            return []

    def purge_old(self) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).date()
        try:
            with self._connect() as connection:
                connection.execute(
                    "DELETE FROM market_prices WHERE price_date < ?", (cutoff.isoformat(),)
                )
        except sqlite3.Error:
            logger.warning("Could not purge price history", exc_info=True)

    def stats(self) -> dict[str, int]:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT COUNT(*) AS n, COUNT(DISTINCT crop_code) AS crops, "
                    "MIN(price_date) AS first, MAX(price_date) AS last FROM market_prices"
                ).fetchone()
            return {
                "observations": row["n"] or 0,
                "crops": row["crops"] or 0,
                "first": row["first"],
                "last": row["last"],
            }
        except sqlite3.Error:
            return {"observations": 0, "crops": 0, "first": None, "last": None}
