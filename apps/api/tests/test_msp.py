"""The MSP reference table.

There are now two files carrying MSP: economics.yaml, which prices the crops
this system ranks, and msp.yaml, which lists every mandated crop for the
lookup tab. Two sources for one number is how a website ends up telling a
farmer 2585 in one place and 2425 in another, so the overlap is asserted here
rather than trusted.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def msp() -> dict:
    return yaml.safe_load((ROOT / "data" / "reference" / "msp.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def economics() -> dict:
    return yaml.safe_load(
        (ROOT / "data" / "reference" / "economics.yaml").read_text(encoding="utf-8")
    )


class TestTheTwoFilesAgree:
    def test_every_shared_crop_carries_the_same_price(self, msp, economics):
        """The whole reason this test file exists."""
        priced = {c["crop_code"]: c for c in msp["crops"] if c.get("crop_code")}
        mismatches = []
        for code, row in priced.items():
            other = (economics.get("crops") or {}).get(code)
            if not other or other.get("price_per_quintal") is None:
                continue
            if other["price_per_quintal"] != row["msp_per_quintal"]:
                mismatches.append(
                    f"{code}: msp.yaml={row['msp_per_quintal']} "
                    f"economics.yaml={other['price_per_quintal']}"
                )
        assert mismatches == [], "MSP disagrees between the two reference files: " + "; ".join(
            mismatches
        )

    def test_every_shared_crop_carries_the_same_cost(self, msp, economics):
        mismatches = []
        for row in msp["crops"]:
            code = row.get("crop_code")
            cost = row.get("cost_a2fl_per_quintal")
            if not code or cost is None:
                continue
            other = (economics.get("crops") or {}).get(code)
            if not other or other.get("cost_a2fl_per_quintal") is None:
                continue
            if other["cost_a2fl_per_quintal"] != cost:
                mismatches.append(f"{code}: {cost} vs {other['cost_a2fl_per_quintal']}")
        assert mismatches == []

    def test_every_priced_crop_in_economics_appears_in_the_lookup(self, msp, economics):
        """Otherwise the tab silently omits a crop the app itself recommends,
        and a farmer looking it up concludes it has no MSP."""
        listed = {c["crop_code"] for c in msp["crops"] if c.get("crop_code")}
        priced = {
            code
            for code, row in (economics.get("crops") or {}).items()
            if row.get("price_per_quintal") is not None
        }
        assert priced - listed == set()


class TestTheDataIsUsable:
    def test_every_row_has_a_price_and_a_source_season(self, msp):
        for row in msp["crops"]:
            assert row.get("msp_per_quintal"), f"{row['name']} has no price"
            assert row.get("season") in {"kharif", "rabi"}, row["name"]

    def test_both_languages_are_present_for_every_crop(self, msp):
        # The tab is bilingual like the rest of the app.
        missing = [c["name"] for c in msp["crops"] if not c.get("name_hi")]
        assert missing == []

    def test_the_sources_are_real_citations(self, msp):
        for key in ("kharif", "rabi"):
            source = msp["sources"][key]
            assert source["url"].startswith("https://www.pib.gov.in/")
            assert source["published"]

    def test_unsourced_crops_carry_no_price(self, msp):
        """Copra, jute and sugarcane are named but not priced.

        An unsourced figure sitting in a table of sourced ones inherits their
        credibility without earning it.
        """
        for row in msp.get("not_listed_here") or []:
            assert "msp_per_quintal" not in row
            assert row.get("note")

    def test_grades_without_published_costs_are_null_not_copied(self, msp):
        """Paddy Grade A and long-staple cotton have no separately compiled
        cost. Copying the other grade's figure would be a different crop's
        number wearing this one's label."""
        for name in ("Paddy (Grade A)", "Jowar (Maldandi)", "Cotton (Long Staple)"):
            row = next(c for c in msp["crops"] if c["name"] == name)
            assert row["cost_a2fl_per_quintal"] is None


class TestTheEndpoint:
    def test_it_serves_the_table(self, client):
        response = client.get("/api/v1/meta/msp")
        assert response.status_code == 200
        body = response.json()
        assert body["marketing_season"] == "2026-27"
        assert len(body["crops"]) >= 20

    def test_it_carries_the_citation_so_the_ui_can_show_it(self, client):
        body = client.get("/api/v1/meta/msp").json()
        assert body["sources"]["kharif"]["url"]
        assert body["sources"]["rabi"]["url"]
