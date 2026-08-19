"""The printed advisory must not depend on which tab was open.

THE REGRESSION THIS GUARDS
--------------------------
The results page was split into Dashboard / Water budget / Risk & planning.
The obvious way to build tabs is to render only the active one. Doing that here
would have quietly gutted the PDF: a farmer on the Dashboard tab pressing
"Download advisory" would have received a document with no water budget and no
risk section, and nothing anywhere would have said they were missing.

So sections stay mounted and are hidden with the `hidden` attribute, and the
print stylesheet reveals them again. That arrangement is easy to undo by
accident — a later refactor "tidying up" the hidden sections into conditional
rendering would look like an improvement and would cost the advisory half its
content.

Checked by reading the source. That is weak, and it is the strongest check
available without a browser test stack for one page.
"""

from __future__ import annotations

from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[3] / "apps" / "web"
TABS = WEB / "src" / "components" / "recommendation" / "result-tabs.tsx"
CSS = WEB / "src" / "app" / "globals.css"
RESULTS_PAGE = WEB / "src" / "app" / "r" / "[request_id]" / "page.tsx"


def css() -> str:
    return CSS.read_text(encoding="utf-8")


def print_block() -> str:
    source = css()
    start = source.index("@media print")
    return source[start:]


class TestSectionsSurvivePrinting:
    def test_sections_are_hidden_not_unmounted(self):
        source = TABS.read_text(encoding="utf-8")
        assert "hidden={" in source, (
            "Tabs appear to render conditionally. Inactive panels must stay in "
            "the DOM or they will be missing from the printed advisory."
        )

    def test_every_section_carries_the_print_marker(self):
        assert "data-result-section" in TABS.read_text(encoding="utf-8")

    def test_the_print_stylesheet_reveals_hidden_sections(self):
        block = print_block()
        assert "[data-result-section][hidden]" in block, (
            "Nothing in @media print un-hides inactive tabs. Whichever tab the "
            "farmer had open would decide what their PDF contained."
        )
        assert "display: block !important" in block

    def test_the_tab_rail_itself_does_not_print(self):
        """Navigation is useless on paper and wastes a column."""
        assert "no-print" in TABS.read_text(encoding="utf-8")


class TestWarningsAreNotFiledUnderATab:
    """A caveat that applies to the whole result must not be reachable only by
    choosing the right tab."""

    def test_warnings_render_outside_the_tabs(self):
        source = RESULTS_PAGE.read_text(encoding="utf-8")
        warnings_at = source.index("<WarningsList")
        tabs_at = source.index("<ResultTabs")
        assert warnings_at < tabs_at, (
            "WarningsList must render above ResultTabs. Inside a tab, a closed "
            "sowing window or an offline notice could be missed entirely."
        )


class TestTheBackgroundDoesNotFollowOntoPaper:
    def test_the_page_tint_is_cleared_for_print(self):
        block = print_block()
        assert "background-image: none !important" in block, (
            "The tinted page background would print as a grey wash across "
            "every sheet."
        )

    @pytest.mark.parametrize("token", ["background-color", "background-image"])
    def test_the_tint_lives_on_the_body_not_on_cards(self, token):
        """Cards stay white so text keeps full contrast on a bright screen."""
        source = css()
        body_start = source.index("body {")
        body_block = source[body_start : source.index("}", body_start)]
        assert token in body_block


class TestTabLabelsAreTranslated:
    @pytest.mark.parametrize("locale", ["en", "hi"])
    @pytest.mark.parametrize("key", ["label", "dashboard", "water", "planning"])
    def test_each_tab_has_a_name_in_both_languages(self, locale, key):
        import json

        path = WEB / "src" / "i18n" / f"{locale}.json"
        assert key in json.loads(path.read_text(encoding="utf-8"))["tabs"]
