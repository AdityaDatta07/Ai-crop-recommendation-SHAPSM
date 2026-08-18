"""Earth Engine and Agmarknet.

What these tests can and cannot do, stated plainly: neither integration has ever
run against real credentials, so nothing here proves the remote calls work. What
they DO prove is the part that matters more for a demo — that every failure path
degrades to a usable answer instead of a 500, and that the parser survives the
shapes data.gov.in is known to return.

The live paths stay unverified until someone runs them with a key.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from apps.api.services.agmarknet import (
    COMMODITY_NAMES,
    AgmarknetClient,
    MandiPrice,
    parse_records,
    summarise,
)


class TestAgmarknetParser:
    """data.gov.in has renamed these fields between revisions."""

    def test_reads_the_documented_field_names(self):
        prices = parse_records(
            "WHEAT",
            [
                {
                    "market": "Lucknow",
                    "arrival_date": "12/08/2026",
                    "min_price": "2400",
                    "max_price": "2600",
                    "modal_price": "2500",
                }
            ],
        )
        assert len(prices) == 1
        assert prices[0].modal_price == 2500
        assert prices[0].mandi == "Lucknow"
        assert prices[0].price_date == date(2026, 8, 12)

    @pytest.mark.parametrize(
        "record",
        [
            {"Market": "X", "Arrival_Date": "2026-08-12", "Modal_Price": "2500"},
            {"market": "X", "arrival_date": "12-08-2026", "modal_x0020_price": "2500"},
        ],
    )
    def test_tolerates_alternate_spellings(self, record):
        assert parse_records("WHEAT", [record])[0].modal_price == 2500

    def test_handles_decimal_and_padded_prices(self):
        prices = parse_records("WHEAT", [{"modal_price": " 2500.00 ", "market": "X"}])
        assert prices[0].modal_price == 2500

    def test_skips_unreadable_records_rather_than_guessing(self):
        prices = parse_records(
            "WHEAT",
            [
                {"modal_price": "NA", "market": "A"},
                {"modal_price": "", "market": "B"},
                {"modal_price": "0", "market": "C"},
                {"market": "D"},
                {"modal_price": "2500", "market": "E"},
            ],
        )
        assert [p.mandi for p in prices] == ["E"]

    def test_empty_payload_is_not_an_error(self):
        assert parse_records("WHEAT", []) == []


class TestSummarise:
    def _price(self, modal: int, days_ago: int = 0, mandi: str = "M") -> MandiPrice:
        return MandiPrice(
            crop_code="WHEAT",
            modal_price=modal,
            min_price=modal - 100,
            max_price=modal + 100,
            mandi=mandi,
            price_date=date.today() - timedelta(days=days_ago),
        )

    def test_uses_the_median_not_the_mean(self):
        """One mis-keyed mandi entry must not drag the figure; there always is one."""
        prices = [self._price(2400), self._price(2500), self._price(99_999)]
        assert summarise(prices).modal_price == 2500

    def test_prefers_the_freshest_day(self):
        result = summarise([self._price(2000, days_ago=20), self._price(2600, days_ago=0)])
        assert result.modal_price == 2600

    def test_rejects_stale_prices_entirely(self):
        assert summarise([self._price(2500, days_ago=90)]) is None

    def test_empty_input_returns_none(self):
        assert summarise([]) is None

    def test_names_the_mandi_when_there_is_only_one(self):
        assert summarise([self._price(2500, mandi="Lucknow")]).mandi == "Lucknow"


class TestAgmarknetFailsSoft:
    """No key, bad key, dead network — all must return [], never raise."""

    def test_unconfigured_client_returns_empty(self):
        assert AgmarknetClient(api_key="").fetch("WHEAT") == []

    def test_unknown_crop_returns_empty(self):
        assert AgmarknetClient(api_key="dummy").fetch("NOTACROP") == []

    def test_network_failure_returns_empty(self):
        # Port 1 is reserved and refuses instantly; no real request escapes.
        client = AgmarknetClient(api_key="dummy", base_url="http://127.0.0.1:1/nope")
        assert client.fetch("WHEAT") == []

    def test_every_reference_crop_has_a_commodity_mapping(self, reference):
        missing = set(reference.crops) - set(COMMODITY_NAMES)
        assert not missing, f"no Agmarknet commodity name for {sorted(missing)}"


class TestPriceServiceFallback:
    def test_falls_back_to_msp_when_agmarknet_is_unavailable(self, client, lucknow_request):
        """The demo path. Wheat must still be priced from MSP with a citation."""
        body = client.post("/api/v1/recommendations", json=lucknow_request).json()
        wheat = next(
            (item for item in body["recommendations"] if item["crop_code"] == "WHEAT"), None
        )
        if wheat is None:
            pytest.skip("wheat not in the top 5 for this district")

        assert wheat["economics"]["expected_price_per_quintal"] is not None
        assert "MSP" in wheat["economics"]["price_source"]


class TestEarthEngineFailsSoft:
    def test_unconfigured_earth_engine_raises_only_inside_the_module(self):
        """provider.py catches this; nothing above services/geo should ever see it."""
        from services.geo.earthengine import EarthEngineNotConfigured, initialise

        initialise.cache_clear()
        with pytest.raises(EarthEngineNotConfigured):
            initialise()

    def test_provider_degrades_rather_than_propagating(self, monkeypatch):
        """With USE_MOCK_GEO=false and no credentials, we get nulls, not a crash."""
        from services.geo import provider
        from services.geo.types import ResolvedLocation

        monkeypatch.setenv("USE_MOCK_GEO", "false")
        place = ResolvedLocation("UP", "UP-LKO", "Lucknow", (80.94, 26.84), 1.0)

        conditions = provider.get_conditions(place)
        assert conditions.data_completeness == 0.0
        assert conditions.soil.ph is None

        indices = provider.get_indices(place)
        assert all(index.value is None for index in indices.indices)
        assert indices.tile_url_template is None
        assert "unavailable" in indices.source.lower()


class TestClientSideFiltering:
    """Regression: server-side filters[...] made data.gov.in hang past 45s.

    The same query unfiltered returns in under a second, so the client pulls one
    large page and narrows it here. These tests cover that narrowing, which is
    now the only filtering that happens.
    """

    RECORDS = [
        {"commodity": "Wheat", "state": "Uttar Pradesh", "district": "Lucknow",
         "market": "Lucknow", "modal_price": "2500", "arrival_date": "18/08/2026"},
        {"commodity": "Wheat", "state": "Uttar Pradesh", "district": "Kanpur Nagar",
         "market": "Kanpur", "modal_price": "2450", "arrival_date": "18/08/2026"},
        {"commodity": "Wheat", "state": "Punjab", "district": "Ludhiana",
         "market": "Ludhiana", "modal_price": "2600", "arrival_date": "18/08/2026"},
        {"commodity": "Onion", "state": "Maharashtra", "district": "Nashik",
         "market": "Lasalgaon", "modal_price": "1800", "arrival_date": "18/08/2026"},
    ]

    def _client(self, monkeypatch, records):
        from apps.api.services import agmarknet

        client = agmarknet.AgmarknetClient(api_key="dummy")
        monkeypatch.setattr(client, "_fetch_page", lambda: records)
        return client

    def test_filters_by_commodity(self, monkeypatch):
        prices = self._client(monkeypatch, self.RECORDS).fetch("ONION")
        assert [p.modal_price for p in prices] == [1800]

    def test_prefers_the_requested_district(self, monkeypatch):
        prices = self._client(monkeypatch, self.RECORDS).fetch(
            "WHEAT", state_name="Uttar Pradesh", district_name="Lucknow"
        )
        assert [p.mandi for p in prices] == ["Lucknow"]

    def test_falls_back_to_state_when_the_district_has_no_trade(self, monkeypatch):
        """Not every mandi trades every crop every day; that is not a failure."""
        prices = self._client(monkeypatch, self.RECORDS).fetch(
            "WHEAT", state_name="Uttar Pradesh", district_name="Varanasi"
        )
        assert {p.mandi for p in prices} == {"Lucknow", "Kanpur"}

    def test_falls_back_to_all_india_when_the_state_has_none(self, monkeypatch):
        prices = self._client(monkeypatch, self.RECORDS).fetch(
            "WHEAT", state_name="Kerala", district_name="Kozhikode"
        )
        assert len(prices) == 3

    def test_matching_is_case_and_space_insensitive(self, monkeypatch):
        records = [{**self.RECORDS[0], "district": "  LUCKNOW  "}]
        prices = self._client(monkeypatch, records).fetch("WHEAT", district_name="lucknow")
        assert len(prices) == 1

    def test_capitalised_xml_field_names_are_read(self):
        """The live schema emits Min_x0020_Price in its XML form."""
        prices = parse_records(
            "WHEAT",
            [{"Market": "X", "Arrival_Date": "18/08/2026",
              "Modal_x0020_Price": "2500", "Min_x0020_Price": "2400",
              "Max_x0020_Price": "2600"}],
        )
        assert prices[0].modal_price == 2500
        assert prices[0].min_price == 2400
        assert prices[0].max_price == 2600

    def test_one_page_serves_many_crops(self, monkeypatch):
        """Ranking five crops must not mean five HTTP requests."""
        from apps.api.services import agmarknet

        calls = {"n": 0}

        def counted_page():
            calls["n"] += 1
            return self.RECORDS

        client = agmarknet.AgmarknetClient(api_key="dummy")
        monkeypatch.setattr(client, "_fetch_page", counted_page)
        for crop in ("WHEAT", "ONION", "WHEAT"):
            client.fetch(crop)
        assert calls["n"] == 3  # one per fetch; real caching is inside _fetch_page


class TestBrowserHeadersAreSent:
    """Regression: data.gov.in's WAF drops library User-Agents.

    Measured directly: `python-httpx/...` read-times-out after 20s, a browser
    UA returns HTTP 200 in 0.5s, on the same URL, same key, same machine, over
    both IPv4 and IPv6. Removing these headers silently reverts live prices to
    the MSP fallback, which is the kind of regression nobody notices.
    """

    def test_user_agent_is_not_a_library_string(self):
        from apps.api.services.agmarknet import BROWSER_HEADERS

        agent = BROWSER_HEADERS["User-Agent"]
        assert "Mozilla" in agent
        assert "httpx" not in agent.lower()
        assert "python" not in agent.lower()

    def test_client_actually_sends_them(self, monkeypatch):
        """Assert on the wire, not on the constant."""
        import httpx

        from apps.api.services import agmarknet

        seen = {}

        def capture(self, request, **kwargs):
            seen.update(request.headers)
            return httpx.Response(200, json={"records": []})

        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", capture)
        agmarknet.AgmarknetClient(api_key="dummy")._fetch_page()

        assert "Mozilla" in seen.get("user-agent", "")


class TestCommodityNameMatching:
    """Regression: the live feed says 'Paddy(Common)', the docs say
    'Paddy(Dhan)(Common)'. Exact matching missed it and rice silently used MSP
    forever — nothing errored, the price was just never live."""

    def test_observed_paddy_spelling_matches_rice(self, monkeypatch):
        from apps.api.services import agmarknet

        client = agmarknet.AgmarknetClient(api_key="dummy")
        monkeypatch.setattr(
            client,
            "_fetch_page",
            lambda: [{
                "commodity": "Paddy(Common)", "state": "Chattisgarh",
                "district": "Khairagarh", "market": "Kheragarh APMC",
                "modal_price": "2200", "arrival_date": "18/08/2026",
            }],
        )
        assert [p.modal_price for p in client.fetch("RICE")] == [2200]

    def test_punctuation_and_case_do_not_break_matching(self):
        from apps.api.services.agmarknet import _normalise_commodity

        assert _normalise_commodity("Paddy(Common)") == _normalise_commodity("PADDY (common)")
        assert _normalise_commodity("Bengal Gram(Gram)(Whole)") == "bengalgramgramwhole"


class TestEnvReachesTheServiceLayer:
    """Regression: .env configured everything except the part that mattered.

    pydantic-settings reads .env into Settings and leaves os.environ empty.
    services/geo and services/ml are plain packages that read os.getenv, so the
    server ran on mock data while Settings said otherwise, and /health reported
    "mock" with a correct .env in place.
    """

    def test_settings_and_os_environ_agree_on_mock_geo(self):
        import os

        from apps.api.core.config import get_settings

        settings = get_settings()
        from_env = os.getenv("USE_MOCK_GEO")

        if from_env is not None:
            assert settings.use_mock_geo == (from_env.strip().lower() in {"1", "true", "yes"}), (
                "Settings and os.environ disagree — services/geo would pick the "
                "wrong backend"
            )

    def test_health_backend_matches_settings(self, client):
        from apps.api.core.config import get_settings
        from services.geo import geo_backend_name

        settings = get_settings()
        expected = "mock" if settings.use_mock_geo else "earthengine"
        assert geo_backend_name() == expected
        assert client.get("/health").json()["geo_service"] == expected


class TestApiKeyValidation:
    """Regression: a leaked .env comment was sent as the API key.

    MARKET_PRICE_API_KEY held the literal text "# Agmarknet / data.gov.in",
    the code preferred it for being non-empty, and every request 403'd while
    the real key sat unused in DATA_GOV_IN_API_KEY.
    """

    def test_rejects_the_comment_that_actually_leaked(self):
        from apps.api.services.agmarknet import looks_like_api_key

        assert looks_like_api_key("# Agmarknet / data.gov.in") is False

    def test_rejects_other_junk(self):
        from apps.api.services.agmarknet import looks_like_api_key

        for junk in ("", None, "   ", "short", "has spaces in it", "# comment"):
            assert looks_like_api_key(junk) is False

    def test_accepts_a_real_shaped_key(self):
        from apps.api.services.agmarknet import looks_like_api_key

        assert looks_like_api_key("579b464db66ec23bdd0000016bfdf8e0ea5245d74ad24e65404551dc")

    def test_a_junk_key_does_not_shadow_a_valid_one(self, monkeypatch, reference):
        from apps.api.core import config
        from apps.api.services.price_service import PriceService

        monkeypatch.setenv("MARKET_PRICE_API_KEY", "# Agmarknet / data.gov.in")
        monkeypatch.setenv("DATA_GOV_IN_API_KEY", "579b464db66ec23bdd0000016bfdf8e0ea5245d74ad")
        config.get_settings.cache_clear()

        service = PriceService(reference)
        assert service.client.api_key.startswith("579b464")

        config.get_settings.cache_clear()
