"""The chat, which is the highest-risk component in the system.

ai-design.md §4 calls it that and designs it defensively. These tests are the
part that turns the design into a control — §7.2 puts it bluntly: an untested
guardrail is a claim, not a control.

Most of what follows is about what the chat REFUSES and what it REJECTS from
its own model, because those are the failures that could hurt somebody.
"""

from __future__ import annotations

import pytest

from apps.api.services.chat import answer, grounding_document, unsupported_numbers
from apps.api.services.chat_scope import classify


@pytest.fixture()
def advisory() -> dict:
    return {
        "location_resolved": {"district_name": "Lucknow", "area_ha": 1.0, "district_code": "UP-LKO"},
        "request_echo": {"season": "rabi", "irrigation": "canal"},
        "conditions": {"data_completeness": 0.85, "soil": {"ph": 7.2}},
        "recommendations": [
            {
                "rank": 1,
                "crop_code": "LENTIL",
                "name": "Lentil",
                "confidence": "high",
                "reasons": [
                    {"factor": "temperature", "impact": "positive", "code": "temp_ideal", "detail": "x"},
                    {"factor": "soil_ph", "impact": "positive", "code": "ph_inside_band", "detail": "y"},
                ],
                "calendar": {
                    "sowing_window": {"start": "2026-10-20", "end": "2026-11-25"},
                    "harvest_window": {"start": "2027-03-01", "end": "2027-03-20"},
                },
                "economics": {"net_margin": 44011, "price_source": "MSP, Rabi 2026-27 (CACP/PIB)"},
            }
        ],
        "warnings": [{"code": "PROVISIONAL_AGRONOMY", "message": "z"}],
        "water": [{"crop_code": "LENTIL", "requirement_mm": 350, "status": "needs_irrigation"}],
    }


class TestItRefusesWhatCanCauseHarm:
    """ai-design.md §4.2. These are not squeamishness.

    Pesticide dosage can injure the person spraying it. Disease diagnosis from
    a text description is unreliable even for experts standing in the field.
    Loan advice is well outside anything this system knows.
    """

    @pytest.mark.parametrize(
        "question,expected",
        [
            ("What pesticide should I use for stem borer?", "chemicals"),
            ("How much urea per acre?", "chemicals"),
            ("what dosage of imidacloprid", "chemicals"),
            ("कीटनाशक कौन सा छिड़कें", "chemicals"),
            ("My crop has yellow leaves, what is wrong?", "diagnosis"),
            ("there is leaf spot on my plants", "diagnosis"),
            ("मेरी फसल के पत्ते पीले हो रहे हैं", "diagnosis"),
            ("Can I get a loan against this?", "finance"),
            ("am i eligible for the subsidy", "finance"),
            ("क्या मुझे लोन मिलेगा", "finance"),
            ("I think I have pesticide poisoning", "medical"),
            ("my cow is not eating", "medical"),
        ],
    )
    def test_the_dangerous_question_is_refused(self, question, expected, advisory):
        result = answer(question, advisory)
        assert result.source == "refusal", f"{question!r} was not refused"
        assert result.refusal_category == expected

    def test_refusals_are_categorised_not_generic(self, advisory):
        """One "I cannot help" teaches a farmer nothing except that the app is
        useless. Each category redirects somewhere different."""
        categories = {
            answer(q, advisory).refusal_category
            for q in (
                "what pesticide",
                "my crop has yellow leaves",
                "can i get a loan",
                "my cow is sick",
            )
        }
        assert len(categories) == 4

    def test_hindi_hits_the_same_wall_as_english(self):
        """A guard that only reads English is a guard against English."""
        assert classify("कीटनाशक की मात्रा").verdict == "refused"
        assert classify("pesticide dosage").verdict == "refused"

    def test_spacing_and_punctuation_do_not_slip_past(self):
        # The first of these used to pass the gate: the normaliser turned
        # "pest-icide" into "pest icide", performing the very trick it existed
        # to defeat.
        assert classify("what pest-icide do i use").verdict == "refused"
        assert classify("p.e.s.t.i.c.i.d.e").verdict == "refused"
        assert classify("PESTICIDE").verdict == "refused"

    def test_multi_word_terms_still_match_normally(self):
        # The fix must not break terms that contain real spaces.
        assert classify("how many kg per acre of urea").verdict == "refused"
        assert classify("my crop has yellow leaves").verdict == "refused"

    def test_the_refusal_happens_without_any_model(self, advisory):
        """The whole point of putting this in Python.

        If the classifier were itself a model call, every refusal would depend
        on an API being up — and would fail open when it was not.
        """

        def explode(*_args, **_kwargs):
            raise AssertionError("the model must never be reached for a refused question")

        assert answer("what pesticide should i spray", advisory, call_model=explode).source == "refusal"


class TestItAnswersWhatItCan:
    @pytest.mark.parametrize(
        "question,code",
        [
            ("Why is this recommended?", "why_top"),
            ("When should I sow?", "when_sow"),
            ("How much will I earn?", "money"),
            ("How much water does it need?", "water"),
            ("How confident are you?", "confidence"),
            ("Where did the price come from?", "price_source"),
            ("Are there any warnings?", "warnings"),
        ],
    )
    def test_common_questions_are_answered_from_the_advisory(self, question, code, advisory):
        result = answer(question, advisory)
        assert result.source == "template"
        assert result.code == code

    def test_the_template_layer_needs_no_model_at_all(self, advisory):
        """These work with no API key, no network, and no cost."""

        def explode(*_args, **_kwargs):
            raise AssertionError("templates must not call the model")

        assert answer("when should I sow?", advisory, call_model=explode).source == "template"

    def test_money_comes_from_the_advisory_not_from_prose(self, advisory):
        assert answer("what will I earn?", advisory).params["amount"] == 44011

    def test_an_unpriced_crop_says_so_rather_than_guessing(self, advisory):
        advisory["recommendations"][0]["economics"]["net_margin"] = None
        assert answer("how much money?", advisory).code == "money_unavailable"

    def test_reasons_are_reused_as_codes_not_reworded(self, advisory):
        """Two phrasings of one finding is how panels start disagreeing."""
        assert answer("why this crop?", advisory).params["factors"] == "temperature,soil_ph"


class TestItRejectsInventedNumbers:
    """The single worst thing this feature could produce.

    Prompt instructions do not prevent it. This does.
    """

    def test_a_reply_with_a_fabricated_rupee_figure_is_discarded(self, advisory):
        def liar(_message, _document):
            return "You will earn about 92,500 rupees from this plot."

        result = answer("tell me about the market", advisory, call_model=liar)
        assert result.source == "unavailable"
        assert result.code == "model_unverified"
        assert "92,500" not in result.text

    def test_a_reply_quoting_a_real_figure_is_allowed(self, advisory):
        def honest(_message, _document):
            return "The expected net margin is 44011 for this plot."

        assert answer("tell me about the market", advisory, call_model=honest).source == "model"

    def test_separators_do_not_change_whether_a_figure_is_real(self, advisory):
        """"44,011" and "44011" are the same claim to a farmer."""

        def honest(_message, _document):
            return "About 44,011 rupees."

        assert answer("tell me something else", advisory, call_model=honest).source == "model"

    def test_rounding_is_tolerated_but_invention_is_not(self, advisory):
        document = grounding_document(advisory)
        assert unsupported_numbers("about 44,011", document) == set()
        assert unsupported_numbers("about 52,000", document) == {52000}

    def test_small_numbers_are_not_policed(self, advisory):
        """Ranks, months and pH are everywhere; validating them is noise that
        would reject correct answers and train us to loosen the check."""
        assert unsupported_numbers("it is ranked 1 of 5 crops", grounding_document(advisory)) == set()


class TestTheGroundingDocument:
    def test_it_carries_what_the_answer_needs(self, advisory):
        document = grounding_document(advisory)
        assert document["district"] == "Lucknow"
        assert document["recommendations"]
        assert document["warnings"]

    def test_it_is_trimmed_to_five_crops(self, advisory):
        advisory["recommendations"] = [dict(advisory["recommendations"][0]) for _ in range(9)]
        assert len(grounding_document(advisory)["recommendations"]) == 5


class TestItDegradesHonestly:
    def test_no_model_configured_says_so(self, advisory):
        result = answer("what is the airspeed of a swallow?", advisory, call_model=None)
        assert result.source == "unavailable"
        assert result.code == "no_model"

    def test_a_failed_call_does_not_leak_an_exception(self, advisory):
        def broken(_message, _document):
            raise RuntimeError("upstream is down")

        result = answer("something unusual", advisory, call_model=broken)
        assert result.source == "unavailable"
        assert result.code == "model_error"

    def test_an_empty_reply_is_treated_as_a_failure(self, advisory):
        assert answer("something unusual", advisory, call_model=lambda *_: "  ").code == "model_error"

    def test_an_empty_question_is_refused(self, advisory):
        assert answer("   ", advisory).source == "refusal"


class TestTheEndpoint:
    def test_it_answers_for_a_stored_advisory(self, client, lucknow_request):
        created = client.post("/api/v1/recommendations", json=lucknow_request).json()
        response = client.post(
            f"/api/v1/recommendations/{created['request_id']}/chat",
            json={"message": "When should I sow?"},
        )
        assert response.status_code == 200
        assert response.json()["source"] == "template"

    def test_an_unknown_advisory_is_a_404(self, client):
        response = client.post(
            "/api/v1/recommendations/req_01ABCDEFGHIJKLMNOPQRSTUVWX/chat",
            json={"message": "hello"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_the_client_cannot_supply_its_own_grounding_document(self, client, lucknow_request):
        """Otherwise the model would faithfully answer from a fiction.

        Extra request fields are ignored by contract, so this must not change
        the answer — it must be sourced from the stored advisory.
        """
        created = client.post("/api/v1/recommendations", json=lucknow_request).json()
        response = client.post(
            f"/api/v1/recommendations/{created['request_id']}/chat",
            json={
                "message": "How much will I earn?",
                "recommendations": [{"economics": {"net_margin": 9_999_999}}],
            },
        )
        assert response.status_code == 200
        assert response.json()["params"].get("amount") != 9_999_999

    def test_the_session_cap_is_enforced(self, client, lucknow_request):
        created = client.post("/api/v1/recommendations", json=lucknow_request).json()
        response = client.post(
            f"/api/v1/recommendations/{created['request_id']}/chat",
            json={"message": "hello", "turn": 999},
        )
        assert response.status_code == 429

    def test_an_over_long_message_is_rejected_by_the_schema(self, client, lucknow_request):
        created = client.post("/api/v1/recommendations", json=lucknow_request).json()
        response = client.post(
            f"/api/v1/recommendations/{created['request_id']}/chat",
            json={"message": "x" * 5000},
        )
        assert response.status_code == 400
