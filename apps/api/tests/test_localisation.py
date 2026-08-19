"""Every message code the server can emit must exist in both dictionaries.

THE BUG THIS EXISTS TO CATCH
----------------------------
Switching the app to Hindi translated the headings and left the sentences in
English — warnings, reasons, verdicts, price explanations. The labels around
the advice were Hindi; the advice itself was not.

The fix was to have the server send a code and the client render it. That moves
the failure rather than removing it: add a message in Python, forget the
dictionary entry, and the farmer silently falls back to English. Nothing throws.
Nothing looks broken in review. It just quietly stops being translated.

So this test walks the source for every code the server can produce and asserts
both en.json and hi.json define it. A new message now fails here, at the point
where it is cheap to fix.

It reads the source rather than exercising the API on purpose: a branch that
only fires for an unpriced crop in a closed sowing window is exactly the one an
end-to-end test would miss.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
WEB_I18N = ROOT / "apps" / "web" / "src" / "i18n"

# group -> (file, how the code appears there)
SOURCES = {
    "reason": ROOT / "services" / "ml" / "ranker.py",
    "warning": ROOT / "apps" / "api" / "services" / "recommendation_service.py",
    "verdict": ROOT / "apps" / "api" / "services" / "comparison.py",
    "outlook": ROOT / "apps" / "api" / "services" / "price_outlook.py",
}

# Codes the frontend raises itself, so they never appear in Python source.
CLIENT_ONLY = {"warning": {"MOCK_DATA", "MOCK_FIXED_AREA", "OFFLINE_RECORDING"}}

# Risk lives under risk.* in the UI dictionaries rather than server.*, because
# the panel owns its own wording. Same guarantee, different prefix.
RISK_VERDICT_SOURCE = ROOT / "apps" / "api" / "services" / "diversification.py"

# `kind` doubles as the counterfactual code; irrigation gets its own wording.
COUNTERFACTUAL_CODES = {
    "threshold",
    "fragility",
    "limiting",
    "irrigation_threshold",
}


def _dictionary(locale: str) -> dict:
    return json.loads((WEB_I18N / f"{locale}.json").read_text(encoding="utf-8"))


def _defined(locale: str, group: str) -> set[str]:
    server = _dictionary(locale).get("server", {})
    # Plural variants are optional; "x_one" is only a variant of "x".
    return {key for key in server.get(group, {}) if not key.endswith("_one")}


def _emitted(group: str) -> set[str]:
    """String literals assigned to the keyword that names a code in that file."""
    keywords = {
        "reason": None,  # returned positionally, handled below
        "warning": "code",
        "verdict": "verdict_code",
        "outlook": "explanation_code",
    }
    tree = ast.parse(SOURCES[group].read_text(encoding="utf-8"))
    found: set[str] = set()

    if group == "reason":
        # Each _*_detail returns (english, code, params). Take the middle item
        # of every 3-tuple whose second element is a plain string.
        for node in ast.walk(tree):
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple):
                parts = node.value.elts
                if len(parts) == 3 and isinstance(parts[1], ast.Constant):
                    if isinstance(parts[1].value, str):
                        found.add(parts[1].value)
        return found

    keyword = keywords[group]
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == keyword:
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                found.add(node.value.value)
        # verdict_code / explanation_code are also set by plain assignment
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == keyword:
                    if isinstance(node.value, ast.Constant) and isinstance(
                        node.value.value, str
                    ):
                        found.add(node.value.value)

    found.discard("")
    return found


@pytest.mark.parametrize("group", sorted(SOURCES))
@pytest.mark.parametrize("locale", ["en", "hi"])
def test_every_emitted_code_has_a_translation(group: str, locale: str) -> None:
    emitted = _emitted(group)
    assert emitted, f"Found no {group} codes in {SOURCES[group].name} — parser out of date?"

    missing = emitted - _defined(locale, group)
    assert not missing, (
        f"{locale}.json has no server.{group} entry for {sorted(missing)}. "
        f"Without it a farmer reading {locale} silently gets English."
    )


@pytest.mark.parametrize("locale", ["en", "hi"])
def test_counterfactual_codes_have_translations(locale: str) -> None:
    missing = COUNTERFACTUAL_CODES - _defined(locale, "counterfactual")
    assert not missing, f"{locale}.json missing server.counterfactual: {sorted(missing)}"


@pytest.mark.parametrize("group", ["warning"])
def test_client_raised_codes_are_translated_too(group: str) -> None:
    for locale in ("en", "hi"):
        missing = CLIENT_ONLY[group] - _defined(locale, group)
        assert not missing, f"{locale}.json missing {group}: {sorted(missing)}"


def test_both_dictionaries_have_identical_keys() -> None:
    """A key present in one language and not the other renders as a raw key path."""

    def flatten(node: dict, prefix: str = "") -> set[str]:
        keys: set[str] = set()
        for key, value in node.items():
            path = f"{prefix}{key}"
            keys |= flatten(value, f"{path}.") if isinstance(value, dict) else {path}
        return keys

    english = flatten(_dictionary("en"))
    hindi = flatten(_dictionary("hi"))
    assert english == hindi, f"Key drift: {sorted(english ^ hindi)}"


@pytest.mark.parametrize("group", sorted(SOURCES) + ["counterfactual"])
def test_placeholders_match_across_languages(group: str) -> None:
    """Hindi must use the same {placeholders} as English.

    A typo here does not crash — it prints "{crop}" to a farmer, which is worse
    than an error because nobody notices until someone reads the printout.
    """
    import re

    english = _dictionary("en")["server"][group]
    hindi = _dictionary("hi")["server"][group]

    for code, template in english.items():
        expected = set(re.findall(r"\{(\w+)\}", template))
        actual = set(re.findall(r"\{(\w+)\}", hindi[code]))
        assert expected == actual, (
            f"server.{group}.{code}: en uses {sorted(expected)}, "
            f"hi uses {sorted(actual)}"
        )


# ---------------------------------------------------------------------- risk


def _risk_codes(keyword: str) -> set[str]:
    tree = ast.parse(RISK_VERDICT_SOURCE.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == keyword:
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                found.add(node.value.value)
    found.discard("")
    return found


def _risk_drivers() -> set[str]:
    """Driver codes are appended to a list, not passed as a keyword."""
    tree = ast.parse(RISK_VERDICT_SOURCE.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "drivers"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            found.add(node.args[0].value)
    return found


@pytest.mark.parametrize("locale", ["en", "hi"])
def test_risk_verdicts_are_translated(locale: str) -> None:
    emitted = _risk_codes("verdict_code")
    assert emitted, "no risk verdict codes found — parser out of date?"

    defined = set(_dictionary(locale).get("risk", {}).get("verdict", {}))
    missing = emitted - defined
    assert not missing, f"{locale}.json missing risk.verdict entries for {sorted(missing)}"


@pytest.mark.parametrize("locale", ["en", "hi"])
def test_risk_drivers_are_translated(locale: str) -> None:
    emitted = _risk_drivers()
    assert emitted, "no driver codes found — parser out of date?"

    defined = set(_dictionary(locale).get("risk", {}).get("driver", {}))
    missing = emitted - defined
    assert not missing, f"{locale}.json missing risk.driver entries for {sorted(missing)}"


@pytest.mark.parametrize("locale", ["en", "hi"])
def test_risk_levels_are_translated(locale: str) -> None:
    defined = set(_dictionary(locale).get("risk", {}).get("level", {}))
    assert {"low", "medium", "high"} <= defined


# ------------------------------------------------------------- crop history

CROP_HISTORY_SOURCE = ROOT / "services" / "ml" / "crop_history.py"


def _crop_history_caveats() -> set[str]:
    """Caveat codes appended to the `caveats` list."""
    tree = ast.parse(CROP_HISTORY_SOURCE.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "caveats"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            found.add(node.args[0].value)
    return found


@pytest.mark.parametrize("locale", ["en", "hi"])
def test_crop_history_caveats_are_translated(locale: str) -> None:
    emitted = _crop_history_caveats()
    assert emitted, "no caveat codes found - parser out of date?"

    defined = set(_dictionary(locale).get("history", {}).get("caveat", {}))
    missing = emitted - defined
    assert not missing, (
        f"{locale}.json missing history.caveat entries for {sorted(missing)}. "
        f"A farmer reading {locale} would see a raw key path."
    )


@pytest.mark.parametrize("locale", ["en", "hi"])
@pytest.mark.parametrize(
    "intensity", ["single", "double", "triple", "fallow", "unknown"]
)
def test_every_intensity_has_a_label_and_a_note(locale: str, intensity: str) -> None:
    history = _dictionary(locale)["history"]
    assert intensity in history["intensity"]
    assert intensity in history["intensityNote"]
