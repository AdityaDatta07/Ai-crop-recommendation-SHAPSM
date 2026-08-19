"""Offline support, checked statically.

There is no JavaScript test runner in this repo, so the service worker and
manifest are verified by reading them. That is weaker than executing them, and
it is chosen deliberately over adding a browser test stack for one feature.

What it does catch is the class of mistake that actually ships: a manifest
pointing at an icon nobody generated, a worker that tries to cache POSTs, a
fixture index that has drifted from the fixtures on disk, and an offline
warning that reaches a Hindi-speaking farmer in English.

The one thing it cannot check is that offline genuinely works in a browser.
That is a manual step: load the app, turn the network off, reload.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[3] / "apps" / "web"
PUBLIC = WEB / "public"
SW = PUBLIC / "sw.js"
MANIFEST = PUBLIC / "manifest.webmanifest"


def sw_source() -> str:
    return SW.read_text(encoding="utf-8")


class TestManifest:
    def test_manifest_exists_and_is_valid_json(self):
        assert MANIFEST.exists(), "no manifest: the app cannot be installed"
        json.loads(MANIFEST.read_text(encoding="utf-8"))

    @pytest.mark.parametrize(
        "field", ["name", "short_name", "start_url", "display", "icons", "theme_color"]
    )
    def test_required_fields_are_present(self, field):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        assert field in data, f"manifest missing {field}; install prompt will not appear"

    def test_every_declared_icon_exists_on_disk(self):
        """A manifest naming a missing icon fails silently — no install prompt,
        no error, nothing to debug."""
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for icon in data["icons"]:
            path = PUBLIC / icon["src"].lstrip("/")
            assert path.exists(), f"manifest references {icon['src']}, which is not there"
            assert path.stat().st_size > 0

    def test_a_maskable_icon_is_provided(self):
        """Android crops non-maskable icons into a circle, cutting the artwork."""
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        assert any("maskable" in icon.get("purpose", "") for icon in data["icons"])

    def test_display_is_standalone(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        assert data["display"] in ("standalone", "fullscreen", "minimal-ui")


class TestServiceWorker:
    def test_the_worker_exists(self):
        assert SW.exists(), (
            "Without a service worker the offline cache is unreachable: getting "
            "to it requires loading the app, which requires the network."
        )

    def test_it_ignores_non_get_requests(self):
        """The Cache API cannot store a POST. A worker that tries to intercept
        the recommendations call would break the request rather than cache it —
        that fallback belongs in offline.ts."""
        assert "request.method !== 'GET'" in sw_source()

    def test_navigations_fall_back_to_the_shell(self):
        """Any route must open offline, including a shared /r/<id> link."""
        source = sw_source()
        assert "'navigate'" in source
        assert "caches.match('/')" in source

    def test_it_does_not_cache_third_party_requests(self):
        """Map tiles are unbounded. Caching them would evict the app itself."""
        assert "url.origin !== self.location.origin" in sw_source()

    def test_the_precache_list_is_not_atomic(self):
        """cache.addAll rejects the whole install if one URL 404s, leaving the
        app with no worker at all. Individual adds degrade instead."""
        source = sw_source()
        assert "allSettled" in source
        # The call, not the word: a comment explaining why addAll is avoided
        # should not fail the check that it is avoided.
        assert ".addAll(" not in source

    def test_it_warms_the_fixture_cache(self):
        """Runtime caching alone only covers districts already visited online."""
        source = sw_source()
        assert "/fixtures/index.json" in source

    def test_the_cache_version_is_a_single_constant(self):
        """Two version strings drift, and a stale cache is a wrong app."""
        assert sw_source().count("const VERSION =") == 1


class TestTheWorkerActuallyShips:
    """A service worker that is not committed is a feature that does not exist.

    The stock Next.js .gitignore excludes public/sw.js, because next-pwa and
    workbox generate one at build time. This project's worker is hand-written
    source. Leaving that rule in place would have deployed an app with no
    offline support and nothing anywhere to say so — it would simply have been
    online-only, silently, forever.
    """

    def test_the_service_worker_is_not_gitignored(self):
        import subprocess

        root = Path(__file__).resolve().parents[3]
        result = subprocess.run(
            ["git", "check-ignore", "apps/web/public/sw.js"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        # Exit code 0 means "this path IS ignored".
        assert result.returncode != 0, (
            "public/sw.js is gitignored. It will never be committed, and the "
            "deployed app will have no offline support."
        )

    def test_the_manifest_is_not_gitignored(self):
        import subprocess

        root = Path(__file__).resolve().parents[3]
        result = subprocess.run(
            ["git", "check-ignore", "apps/web/public/manifest.webmanifest"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0, "manifest is gitignored; the app cannot be installed"


class TestFixtureIndex:
    """The index the worker precaches from must match what is on disk."""

    def _index(self) -> list[str]:
        path = PUBLIC / "fixtures" / "index.json"
        if not path.exists():
            pytest.skip("fixtures not synced; run npm run sync:fixtures")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_every_indexed_fixture_exists(self):
        for entry in self._index():
            assert (PUBLIC / entry.lstrip("/")).exists(), f"index lists missing {entry}"

    def test_every_fixture_on_disk_is_indexed(self):
        """A fixture missing from the index is simply never available offline."""
        indexed = set(self._index())
        on_disk = {
            "/fixtures/" + str(p.relative_to(PUBLIC / "fixtures")).replace("\\", "/")
            for p in (PUBLIC / "fixtures").rglob("*.json")
            if p.name != "index.json"
        }
        assert on_disk == indexed, f"index out of step: {sorted(on_disk ^ indexed)}"

    def test_the_offline_payload_stays_small(self):
        """A phone on a rural connection has to download this once."""
        total = sum(
            p.stat().st_size for p in (PUBLIC / "fixtures").rglob("*.json")
        )
        assert total < 5_000_000, f"offline payload is {total / 1e6:.1f} MB"


class TestOfflineCopyIsTranslated:
    """An offline farmer reading Hindi must not be told so in English."""

    def _dictionary(self, locale: str) -> dict:
        path = WEB / "src" / "i18n" / f"{locale}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    @pytest.mark.parametrize("locale", ["en", "hi"])
    def test_the_offline_recording_warning_is_translated(self, locale):
        warnings = self._dictionary(locale)["server"]["warning"]
        assert "OFFLINE_RECORDING" in warnings

    @pytest.mark.parametrize("locale", ["en", "hi"])
    @pytest.mark.parametrize("key", ["banner", "title", "body", "retry", "home"])
    def test_the_offline_screen_is_translated(self, locale, key):
        assert key in self._dictionary(locale)["offline"]


class TestTheFallbackIsAFallbackNotAMode:
    """Offline data must never pre-empt a working connection."""

    def _client(self) -> str:
        return (WEB / "src" / "lib" / "client.ts").read_text(encoding="utf-8")

    def test_recommendations_use_the_offline_fallback(self):
        assert "withOfflineFallback" in self._client()

    def test_saved_results_are_not_served_from_a_district_recording(self):
        """A recording under someone else's request_id would attach a
        stranger's advice to their shareable link."""
        source = self._client()
        start = source.index("getRecommendationById")
        body = source[start : start + 400]
        assert "withOfflineFallback" not in body

    def test_the_live_call_is_attempted_first(self):
        offline = (WEB / "src" / "lib" / "offline.ts").read_text(encoding="utf-8")
        assert "return await live();" in offline

    def test_only_reachability_failures_fall_back(self):
        """A 422 is a real answer and must reach the farmer, not be replaced by
        a recording that happens to look nicer."""
        offline = (WEB / "src" / "lib" / "offline.ts").read_text(encoding="utf-8")
        assert "isRecoverableOffline" in offline


class TestNoSubstitutionIsSilent:
    """Every fallback must announce itself.

    The field-summary call has a 15-second timeout and Earth Engine's cold
    start regularly exceeds it. TIMEOUT counts as a reachability failure, so
    the fallback fired and served a stored recording for the district — soil,
    rainfall, NDVI — with nothing on screen to say so. The satellite service
    was working. It was merely slow.

    The mock source strings do end in "(mocked)", which is why this survived
    review: it looks like provenance, not a warning. A farmer scanning a page
    of sourced figures has no reason to read that one differently.
    """

    def _offline_ts(self) -> str:
        return (WEB / "src" / "lib" / "offline.ts").read_text(encoding="utf-8")

    def test_the_fallback_marks_what_it_substituted(self):
        source = self._offline_ts()
        assert "offline_recording" in source, (
            "withOfflineFallback returns recorded data without marking it. "
            "A substitution the reader cannot detect is the worst outcome here."
        )

    def test_the_conditions_panel_can_show_the_marker(self):
        panel = (
            WEB / "src" / "components" / "recommendation" / "conditions-panel.tsx"
        ).read_text(encoding="utf-8")
        assert "recorded" in panel
        assert "conditions.recorded" in panel

    def test_the_form_passes_the_marker_through(self):
        """The flag existing is not enough; it has to reach the panel."""
        form = (
            WEB / "src" / "components" / "recommendation" / "recommendation-form.tsx"
        ).read_text(encoding="utf-8")
        assert "offline_recording" in form

    @pytest.mark.parametrize("locale", ["en", "hi"])
    def test_the_notice_is_translated(self, locale):
        import json

        path = WEB / "src" / "i18n" / f"{locale}.json"
        assert "recorded" in json.loads(path.read_text(encoding="utf-8"))["conditions"]
