"""District crowding.

The bug this feature could cause is not a crash or a wrong number. It is a
number that is *correct* and read as something else: a count of advisories this
tool issued, understood as a count of farmers who are about to sow.

That misreading is the entire reason the original feature was cut down. So
roughly half of these tests are about wording rather than arithmetic, which is
unusual and deliberate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.api.services.crowding import (
    MIN_ADVISORIES,
    build,
    concentration,
    harvest_dip,
)
from apps.api.services.price_outlook import MIN_OBSERVATIONS_FOR_SEASONAL

ROOT = Path(__file__).resolve().parents[3]


class TestConcentrationBands:
    @pytest.mark.parametrize(
        "first,total,expected",
        [
            (10, 12, "crowded"),
            (6, 12, "crowded"),
            (5, 12, "common"),
            (3, 12, "common"),
            (2, 12, "uncommon"),
            (0, 12, "never"),
        ],
    )
    def test_a_crop_lands_in_the_right_band(self, first, total, expected):
        assert concentration("WHEAT", times_ranked_first=first, advisories_total=total).band == expected

    def test_the_share_is_out_of_all_advisories_not_just_this_crop(self):
        """Dividing by the crops we happened to look at would make every share
        100%, since a crop is only shown when it was recommended."""
        result = concentration("WHEAT", times_ranked_first=3, advisories_total=12)
        assert result.share == pytest.approx(0.25)

    def test_the_percent_shown_matches_the_share(self):
        result = concentration("WHEAT", times_ranked_first=9, advisories_total=12)
        assert result.params["percent"] == 75
        assert result.share == pytest.approx(0.75)


class TestItRefusesToSpeakOnThinData:
    def test_below_the_minimum_there_is_no_share_at_all(self):
        """Not a low-confidence share. No share.

        A percentage on screen is read as a measurement whatever badge sits
        next to it, and 3 out of 4 is not a measurement of anything.
        """
        result = concentration("WHEAT", times_ranked_first=3, advisories_total=4)
        assert result.share is None
        assert result.band == "unknown"

    def test_the_refusal_names_the_count(self):
        """"Not enough data" alone hides how close we are. Seven is nearly
        there; one is not, and the reader should be able to tell."""
        result = concentration("WHEAT", times_ranked_first=1, advisories_total=7)
        assert result.params["advisories"] == 7
        assert result.params["needed"] == MIN_ADVISORIES

    def test_an_empty_district_is_not_zero_percent(self):
        result = concentration("WHEAT", times_ranked_first=0, advisories_total=0)
        assert result.share is None
        assert result.band == "unknown"

    def test_the_minimum_is_tied_to_the_band_width(self):
        """The threshold is derived, not chosen: one advisory must move the
        share by less than half a band width, or the bands are noise.

        If someone widens the bands without revisiting MIN_ADVISORIES, this
        fails and says why.
        """
        from apps.api.services.crowding import COMMON_SHARE, CROWDED_SHARE

        band_width = CROWDED_SHARE - COMMON_SHARE
        assert 1 / MIN_ADVISORIES <= band_width / 2


class TestHarvestDip:
    def test_a_steep_dip_is_detected(self):
        result = harvest_dip(
            "ONION",
            harvest_month=4,
            harvest_month_prices=[800] * 10,
            other_month_prices=[1200] * 10,
        )
        assert result.band == "steep"
        assert result.dip_fraction == pytest.approx(0.333, abs=0.01)

    def test_a_flat_year_is_not_a_dip(self):
        result = harvest_dip(
            "WHEAT",
            harvest_month=4,
            harvest_month_prices=[2000] * 10,
            other_month_prices=[2020] * 10,
        )
        assert result.band == "none"

    def test_a_price_rise_at_harvest_is_not_reported_as_a_dip(self):
        result = harvest_dip(
            "WHEAT",
            harvest_month=4,
            harvest_month_prices=[2400] * 10,
            other_month_prices=[2000] * 10,
        )
        assert result.band == "none"

    def test_medians_not_means(self):
        """One freak entry in a thin sample should not decide the band."""
        result = harvest_dip(
            "WHEAT",
            harvest_month=4,
            harvest_month_prices=[2000] * 9 + [200_000],
            other_month_prices=[2000] * 10,
        )
        assert result.band == "none"

    def test_it_uses_the_same_minimum_as_the_price_outlook(self):
        """Two panels on one screen must not disagree about whether there is
        enough price history to speak."""
        thin = harvest_dip(
            "WHEAT",
            harvest_month=4,
            harvest_month_prices=[2000] * (MIN_OBSERVATIONS_FOR_SEASONAL - 1),
            other_month_prices=[2400] * 20,
        )
        assert thin.band == "unknown"

    def test_both_sides_need_history_not_just_the_harvest_month(self):
        """Plenty of harvest prices against three from the rest of the year is
        a confident comparison with nothing to compare against."""
        result = harvest_dip(
            "WHEAT",
            harvest_month=4,
            harvest_month_prices=[2000] * 30,
            other_month_prices=[2400] * 3,
        )
        assert result.band == "unknown"

    def test_no_harvest_month_means_no_comparison(self):
        result = harvest_dip(
            "WHEAT", harvest_month=None, harvest_month_prices=[2000] * 20,
            other_month_prices=[2400] * 20,
        )
        assert result.band == "unknown"

    def test_a_refusal_does_not_understate_what_we_hold(self):
        """The screen said "0 from the rest of the year" for a crop with 360.

        `harvest_month_comparison` returned empty lists whenever it could not
        make the comparison, discarding counts it had just measured. The
        refusal was correct; the sentence built from it was false. A farmer
        reading it would conclude the app knows nothing about that crop's
        price, when in fact it is only missing one month.
        """
        result = harvest_dip(
            "CHICKPEA",
            harvest_month=4,
            harvest_month_prices=[],
            other_month_prices=[5000] * 360,
        )
        assert result.band == "unknown"
        assert result.params["other_seen"] == 360, "the refusal understated what we hold"
        assert result.params["harvest_seen"] == 0

    def test_a_missing_harvest_month_reads_differently_from_a_new_install(self):
        """Waiting for April is not the same as having nothing.

        Both refuse, but one is "come back after harvest" and the other is
        "this app is new". Collapsing them into one message threw away the
        only part a reader could act on.
        """
        waiting = harvest_dip(
            "CHICKPEA", harvest_month=4, harvest_month_prices=[], other_month_prices=[5000] * 360
        )
        brand_new = harvest_dip(
            "CHICKPEA", harvest_month=4, harvest_month_prices=[5000] * 2, other_month_prices=[5000] * 3
        )
        assert waiting.code == "harvest_month_not_seen_yet"
        assert brand_new.code == "too_little_price_history"
        assert waiting.code != brand_new.code

    def test_a_refused_comparison_reports_no_scope(self):
        """Otherwise the UI shows "based on district prices" beside no number."""
        result = harvest_dip(
            "WHEAT", harvest_month=4, harvest_month_prices=[], other_month_prices=[],
            scope="district",
        )
        assert result.scope == "none"


class TestTheCaveatsAreAlwaysAttached:
    def _built(self, **kwargs):
        defaults = dict(
            times_ranked_first=6,
            advisories_total=12,
            harvest_month=4,
            harvest_month_prices=[800] * 10,
            other_month_prices=[1200] * 10,
        )
        defaults.update(kwargs)
        return build("ONION", **defaults)

    def test_the_advisories_not_farmers_caveat_is_never_omitted(self):
        """The single most likely misreading of this whole panel."""
        assert "advisories_not_farmers" in self._built().caveat_codes
        assert "advisories_not_farmers" in self._built(advisories_total=2).caveat_codes
        assert "advisories_not_farmers" in self._built(harvest_month=None).caveat_codes

    def test_a_reported_dip_is_flagged_as_history(self):
        assert "dip_is_backward_looking" in self._built().caveat_codes

    def test_no_dip_means_no_backward_looking_caveat(self):
        """A caveat about a number that is not on screen is noise, and noise
        trains people to skip the caveats that matter."""
        result = self._built(harvest_month_prices=[], other_month_prices=[])
        assert "dip_is_backward_looking" not in result.caveat_codes

    def test_national_prices_are_flagged_as_not_local(self):
        result = self._built(price_scope="national")
        assert "prices_not_local" in result.caveat_codes

    def test_district_prices_carry_no_such_flag(self):
        assert "prices_not_local" not in self._built().caveat_codes


class TestNothingClaimsToCountFarmers:
    """The guard that protects the decision this feature was rebuilt around.

    We cannot see what anyone plants. Every phrase must count ADVISORIES. This
    reads the shipped English strings, because that is what a farmer actually
    sees — a correctly-named Python field with "62% of farmers" in its
    translation would pass every other test in this file.
    """

    FORBIDDEN = ("farmer", "plot", "hectare", "sown", "sowing", "planting", "growers", "acre")

    #: The disclaimers are the one place these words belong, because their
    #: whole job is to deny the reading. Exempting them would normally weaken
    #: the guard, so `test_the_disclaimer_actually_denies_it` checks that the
    #: denial is really in there — the exemption is itself guarded.
    DISCLAIMERS = ("advisories_not_farmers", "dip_is_backward_looking", "prices_not_local")

    def _english(self) -> dict:
        """Both halves of the panel's vocabulary.

        Panel chrome lives under `crowding`; the prose the server generates
        codes for lives under `server.crowding` so it goes through the money
        formatter and the crop-name resolver. Scanning only one of them would
        leave half the sentences on the screen unguarded.
        """
        text = (ROOT / "apps" / "web" / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
        data = json.loads(text)
        return {**data.get("crowding", {}), **data.get("server", {}).get("crowding", {})}

    def _flat(self, node, prefix="") -> dict:
        out = {}
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                out.update(self._flat(value, path))
            else:
                out[path] = str(value)
        return out

    def test_the_crowding_dictionary_exists(self):
        assert self._english(), "no crowding block in en.json — this guard is blind"

    def test_no_crowding_string_describes_farmers_or_land(self):
        offenders = []
        for key, value in self._flat(self._english()).items():
            if key in self.DISCLAIMERS:
                continue
            lowered = value.lower()
            for word in self.FORBIDDEN:
                if word in lowered:
                    offenders.append((key, word, value))
        assert offenders == [], (
            "A crowding string claims to describe farmers or land. We have no "
            "visibility of what anyone sows; these numbers count advisories "
            "this tool issued. Reword it. Offenders: " + repr(offenders)
        )

    def test_the_disclaimer_actually_denies_it(self):
        """Guards the exemption above.

        `advisories_not_farmers` is skipped by the wording check, so if it were
        reworded into something vague the panel would lose its only defence
        against the misreading and no test would notice. It has to keep both
        halves: what the number IS, and what it is not.
        """
        text = self._flat(self._english())["advisories_not_farmers"].lower()
        assert "advisor" in text, "must say what is actually being counted"
        assert "not" in text, "must say what it is not"
        assert any(word in text for word in ("sown", "planted", "farmer")), (
            "must name the reading it is denying, or the denial is abstract"
        )

    def test_the_word_advisories_actually_appears(self):
        """The complement of the test above: it is trivially satisfiable by
        saying nothing at all. Something must name what is being counted."""
        joined = " ".join(self._flat(self._english()).values()).lower()
        assert "advisor" in joined

    def test_every_emitted_code_resolves_through_the_client_lookup(self):
        """Exercises the real functions and the real key construction.

        THIS TEST USED TO BE A LIST, AND THE LIST WAS WRONG
        ---------------------------------------------------
        The first version wrote out the codes it expected and checked those
        against en.json. Both sides agreed, it passed — and the panel shipped
        blank, because the codes the module ACTUALLY emitted were prefixed
        ("crowding.advice_crowded"), the client resolves them as
        `server.<group>.<code>`, and the result was
        `server.crowding.crowding.advice_crowded`. Nothing matched, the empty
        fallback rendered, and no test noticed because no test ever compared an
        emitted code with a dictionary key.

        So this one calls the functions, collects what comes out, and resolves
        each through the same path the browser uses. It cannot agree with a
        mistake it made itself.
        """
        emitted = self._emitted_codes()
        assert len(emitted) >= 10, f"only collected {sorted(emitted)} — the sweep may have broken"

        dictionaries = self._dictionaries()
        problems = []
        for locale, data in dictionaries.items():
            block = data.get("server", {}).get("crowding", {})
            for code in sorted(emitted):
                # Exactly what apps/web/src/i18n/server-text.ts does:
                #   const key = `server.${group}.${code}`
                text = block.get(code)
                if not text:
                    problems.append(f"{locale}: server.crowding.{code} is missing or empty")
        assert problems == [], "\n".join(problems)

    def test_no_emitted_code_carries_its_own_group_prefix(self):
        """The specific mistake, named, so the next person cannot repeat it."""
        offenders = sorted(c for c in self._emitted_codes() if c.startswith("crowding."))
        assert offenders == [], (
            "Codes must be bare. The client builds `server.crowding.<code>`, so "
            f"these would resolve to server.crowding.crowding.*: {offenders}"
        )

    def _dictionaries(self) -> dict:
        base = ROOT / "apps" / "web" / "src" / "i18n"
        return {
            name: json.loads((base / f"{name}.json").read_text(encoding="utf-8"))
            for name in ("en", "hi")
        }

    def test_the_sweep_reaches_every_band_the_types_allow(self):
        """Guards the guard.

        `_emitted_codes` only checks the codes it manages to provoke. When the
        "never" band was added, the sweep had no zero case, so the new band and
        its untranslated string were invisible to a test whose entire job was
        finding untranslated strings — it passed while the panel would have
        rendered blank.

        Reading the bands out of the Literal means a band added tomorrow fails
        here until the sweep is extended to reach it.
        """
        import typing

        from apps.api.services.crowding import ConcentrationBand, DipBand, build

        expected = set(typing.get_args(ConcentrationBand)) | set(typing.get_args(DipBand))
        expected.discard("unknown")  # reached by the refusal cases, not a code suffix

        reached = set()
        for code in self._emitted_codes():
            for prefix in ("advice_", "dip_"):
                if code.startswith(prefix):
                    reached.add(code[len(prefix) :])

        missing = sorted(expected - reached)
        assert missing == [], (
            f"the sweep never produces these bands, so their translations are "
            f"unchecked: {missing}"
        )
        assert build  # the sweep must go through the real entry point

    def _emitted_codes(self) -> set[str]:
        """Every code the module can produce, by actually producing them."""
        from apps.api.services.crowding import MIN_ADVISORIES, build

        deep = [1000] * (MIN_OBSERVATIONS_FOR_SEASONAL + 4)
        codes: set[str] = set()

        cases = [
            # Each concentration band, by varying how often the crop led.
            dict(times_ranked_first=10, advisories_total=12),   # crowded
            dict(times_ranked_first=4, advisories_total=12),    # common
            dict(times_ranked_first=1, advisories_total=12),    # uncommon
            dict(times_ranked_first=0, advisories_total=12),    # never
            dict(times_ranked_first=1, advisories_total=2),     # too_few_advisories
        ]
        dips = [
            # Each dip band, plus both refusals.
            dict(harvest_month=4, harvest_month_prices=[700] * 12, other_month_prices=deep),
            dict(harvest_month=4, harvest_month_prices=[920] * 12, other_month_prices=deep),
            dict(harvest_month=4, harvest_month_prices=[1000] * 12, other_month_prices=deep),
            dict(harvest_month=4, harvest_month_prices=[], other_month_prices=[]),
            dict(harvest_month=None, harvest_month_prices=deep, other_month_prices=deep),
        ]

        for case in cases:
            for dip in dips:
                for scope in ("district", "national"):
                    for seeded in (0, 5):
                        result = build(
                            "WHEAT",
                            **case,
                            **dip,
                            price_scope=scope,
                            seeded_advisories=seeded,
                        )
                        codes.add(result.concentration.code)
                        codes.add(result.dip.code)
                        codes.update(result.caveat_codes)

        assert MIN_ADVISORIES  # referenced so the import cannot rot silently
        return {code for code in codes if code}
