"""Farmer Q&A about one advisory. ai-design.md Layer 3.

THE ORDER OF OPERATIONS IS THE DESIGN
-------------------------------------
    scope gate  ->  deterministic answer  ->  model  ->  numeric validation

Every step can stop the one after it, and every step can answer on its own.
That is what makes the feature safe to ship next to numbers a farmer will act
on:

1. **Scope gate** (chat_scope.py). Pure Python, no network. Pesticide dosage
   and disease diagnosis are refused here, so the refusal holds when the model
   API is down, rate-limited, or has been talked into a different mood.

2. **Deterministic answer.** Common questions — why this crop, when to sow,
   what will I earn, how much water — are answered from the advisory JSON by
   code. No model is called at all. These answers cannot be wrong unless the
   advisory is wrong, and they work with no API key and no network.

3. **Model**, only for what the templates do not cover, and only with the
   advisory as its entire world.

4. **Numeric validation.** Any figure in the reply that is not in the grounding
   document fails the whole response and we fall back to step 2. An invented
   rupee figure is the single worst thing this feature could produce, and
   prompt instructions alone do not prevent it.

WHY THE DETERMINISTIC LAYER IS NOT JUST A FALLBACK
--------------------------------------------------
It runs BEFORE the model, not after it. The questions farmers ask most are the
ones we can answer exactly, and routing those through a language model would
add cost, latency and a hallucination surface in exchange for nicer phrasing.
The model earns its place on the long tail, not on "when do I sow".
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from apps.api.services.chat_scope import ScopeDecision, classify

logger = logging.getLogger(__name__)

AnswerSource = Literal["refusal", "template", "model", "unavailable"]

#: Figures below this are ranks, counts, months, pH — they appear everywhere
#: and validating them produces noise. Money, yields and areas are what a
#: farmer acts on and what an invented number would corrupt.
NUMERIC_VALIDATION_FLOOR = 100


@dataclass
class ChatAnswer:
    source: AnswerSource
    #: i18n code under `server.chat.*`, rendered client-side. Empty when the
    #: model answered, because free prose has no code.
    code: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    #: Free text, only ever from the model, only after validation.
    text: str = ""
    refusal_category: str | None = None


# --------------------------------------------------------------- grounding


def grounding_document(payload: dict) -> dict:
    """Everything the model is allowed to know, and nothing else.

    Trimmed to the top five crops per ai-design.md §6 — the full candidate set
    triples the prompt for crops the farmer was never shown.
    """
    return {
        "district": (payload.get("location_resolved") or {}).get("district_name"),
        "area_ha": (payload.get("location_resolved") or {}).get("area_ha"),
        "season": (payload.get("request_echo") or {}).get("season"),
        "irrigation": (payload.get("request_echo") or {}).get("irrigation"),
        "conditions": payload.get("conditions"),
        "recommendations": (payload.get("recommendations") or [])[:5],
        "warnings": payload.get("warnings") or [],
        "water": payload.get("water") or [],
    }


def _numbers(text: str) -> set[int]:
    """Integers worth validating, with separators removed.

    "₹45,000" and "45000" are the same claim; a farmer reading either would act
    identically, so they must compare equal here.
    """
    found: set[int] = set()
    for raw in re.findall(r"\d[\d,]*", text):
        digits = raw.replace(",", "")
        if not digits:
            continue
        value = int(digits)
        if value >= NUMERIC_VALIDATION_FLOOR:
            found.add(value)
    return found


def unsupported_numbers(reply: str, document: dict) -> set[int]:
    """Figures the model stated that are not in its grounding document.

    Rounding is tolerated in one direction only: a model that says "about
    45,000" for 45,123 is summarising, which is fine and useful. A model that
    says 52,000 is inventing. So a stated figure passes if it is within 1% of
    something real, and fails otherwise.
    """
    allowed = _numbers(json.dumps(document, default=str))
    bad: set[int] = set()
    for stated in _numbers(reply):
        if any(abs(stated - real) <= max(1, real * 0.01) for real in allowed):
            continue
        bad.add(stated)
    return bad


# ------------------------------------------------------- deterministic layer
#
# Intent detection is keyword-based on purpose. It is inspectable, it is
# instant, and when it does not recognise a question it simply declines to
# answer and lets the next layer try — so a miss costs nothing.

_INTENTS: list[tuple[str, list[str]]] = [
    ("why_top", ["why", "क्यों", "kyu", "kyun", "reason", "कारण"]),
    ("when_sow", ["when", "sow", "sowing", "plant", "कब", "बुवाई", "बोना"]),
    ("money", ["earn", "profit", "money", "margin", "income", "कमाई", "मुनाफ", "आय", "लाभ"]),
    ("water", ["water", "irrigat", "rain", "पानी", "सिंचाई", "बारिश"]),
    ("confidence", ["confiden", "sure", "certain", "trust", "भरोसा", "विश्वास", "पक्का"]),
    ("price_source", ["price come", "where did", "source", "भाव कहां", "भाव कहाँ", "स्रोत"]),
    ("warnings", ["warning", "caution", "risk", "चेतावनी", "जोखिम"]),
]


def _detect_intent(message: str) -> str | None:
    text = message.casefold()
    for intent, keys in _INTENTS:
        if any(key in text for key in keys):
            return intent
    return None


def template_answer(message: str, payload: dict) -> ChatAnswer | None:
    """Answer from the advisory itself, or decline by returning None."""
    intent = _detect_intent(message)
    if intent is None:
        return None

    recommendations = payload.get("recommendations") or []
    if not recommendations:
        return None
    top = recommendations[0]
    economics = top.get("economics") or {}
    calendar = top.get("calendar") or {}
    place = payload.get("location_resolved") or {}

    if intent == "why_top":
        reasons = [r for r in (top.get("reasons") or []) if r.get("impact") == "positive"]
        if not reasons:
            return None
        return ChatAnswer(
            source="template",
            code="why_top",
            params={
                "crop": top.get("name"),
                "crop_code": top.get("crop_code"),
                # FACTOR NAMES, not reason codes.
                #
                # The reason codes render with their own numeric params ("pH
                # 7.2 sits inside wheat's band"), which this sentence does not
                # carry — they would come out with visible {ph} holes in them.
                # Factor names are self-contained, already translated in
                # `factors.*`, and the sentence points at the Dashboard for the
                # figures rather than restating them in a second wording.
                "factors": ",".join(r.get("factor", "") for r in reasons[:3] if r.get("factor")),
            },
        )

    if intent == "when_sow":
        window = calendar.get("sowing_window") or {}
        if not window.get("start"):
            return None
        return ChatAnswer(
            source="template",
            code="when_sow",
            params={
                "crop": top.get("name"),
                "crop_code": top.get("crop_code"),
                "start": window.get("start"),
                "end": window.get("end"),
            },
        )

    if intent == "money":
        if economics.get("net_margin") is None:
            return ChatAnswer(
                source="template",
                code="money_unavailable",
                params={"crop": top.get("name"), "crop_code": top.get("crop_code")},
            )
        return ChatAnswer(
            source="template",
            code="money",
            params={
                "crop": top.get("name"),
                "crop_code": top.get("crop_code"),
                "amount": int(economics["net_margin"]),
                "area": place.get("area_ha"),
            },
        )

    if intent == "water":
        budgets = payload.get("water") or []
        budget = next((b for b in budgets if b.get("crop_code") == top.get("crop_code")), None)
        if budget is None:
            return None
        return ChatAnswer(
            source="template",
            code="water",
            params={
                "crop": top.get("name"),
                "crop_code": top.get("crop_code"),
                "requirement": budget.get("requirement_mm"),
                "status": budget.get("status"),
            },
        )

    if intent == "confidence":
        return ChatAnswer(
            source="template",
            code="confidence",
            params={
                "crop": top.get("name"),
                "crop_code": top.get("crop_code"),
                "level": top.get("confidence"),
                "completeness": round((payload.get("conditions") or {}).get("data_completeness", 0) * 100),
            },
        )

    if intent == "price_source":
        return ChatAnswer(
            source="template",
            code="price_source",
            params={
                "crop": top.get("name"),
                "crop_code": top.get("crop_code"),
                "source": economics.get("price_source") or "unknown",
            },
        )

    if intent == "warnings":
        warnings = payload.get("warnings") or []
        return ChatAnswer(
            source="template",
            code="warnings" if warnings else "warnings_none",
            params={"count": len(warnings)},
        )

    return None


# ------------------------------------------------------------- orchestration


def answer(
    message: str,
    payload: dict,
    *,
    call_model=None,
) -> ChatAnswer:
    """Produce an answer, or a reason for not producing one.

    `call_model` is injected so this whole function is testable without a
    network, a key, or a bill. Production passes the provider client; tests
    pass a stub, and one test passes a deliberately misbehaving stub to prove
    the numeric validation actually rejects it.
    """
    decision: ScopeDecision = classify(message)
    if decision.verdict == "refused":
        logger.info("chat refused: category=%s term=%r", decision.category, decision.matched)
        return ChatAnswer(
            source="refusal",
            code=decision.code,
            refusal_category=decision.category,
        )

    templated = template_answer(message, payload)
    if templated is not None:
        return templated

    if call_model is None:
        # No key configured, or the caller chose not to use one. Say what this
        # can answer rather than pretending the question was unanswerable.
        return ChatAnswer(source="unavailable", code="no_model")

    document = grounding_document(payload)
    try:
        reply = call_model(message, document)
    except Exception:
        logger.exception("chat model call failed")
        return ChatAnswer(source="unavailable", code="model_error")

    reply = (reply or "").strip()
    if not reply:
        return ChatAnswer(source="unavailable", code="model_error")

    invented = unsupported_numbers(reply, document)
    if invented:
        # Do not show it, do not repair it, do not explain it away. A reply
        # containing one invented rupee figure is not partially useful.
        logger.warning("chat reply rejected; unsupported figures %s", sorted(invented))
        return ChatAnswer(source="unavailable", code="model_unverified")

    return ChatAnswer(source="model", text=reply)
