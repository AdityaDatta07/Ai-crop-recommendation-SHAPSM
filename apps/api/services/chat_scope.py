"""What the chat will and will not answer, decided before any model runs.

WHY THIS IS A SEPARATE, DETERMINISTIC MODULE
--------------------------------------------
ai-design.md §4.4 asks for four layers of defence and puts an input classifier
first. The obvious way to build that classifier is another LLM call. That is
also the wrong way round for the questions that matter most: "how much urad
should I spray" must be refused whether or not the classifier API is up,
whether or not it is rate-limited, and whether or not somebody has talked the
classifier into a different mood.

So the refusals that exist to prevent harm are keyword rules in Python. They
are crude, they over-refuse, and they cannot be argued with — which for
pesticide dosage is exactly the right trade. The model, when configured, runs
only on what survives this gate, and is told the same boundaries again.

WHY REFUSALS ARE CATEGORISED
----------------------------
A single "I cannot help with that" teaches a farmer nothing except that the app
is useless. Each category returns its own reason and its own redirect, because
"I cannot recommend a pesticide, an agronomist has to see the field" and "I do
not know anything about your loan eligibility" are different sentences that
send the person to different places.

THE WORD LISTS ARE BILINGUAL
----------------------------
A farmer typing in Hindi must hit the same wall as one typing in English. A
guard that only reads English is not a guard, it is a guard against English.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

RefusalCategory = Literal[
    "chemicals",
    "diagnosis",
    "finance",
    "medical",
    "other_field",
]

Verdict = Literal["allowed", "refused"]


@dataclass(frozen=True)
class ScopeDecision:
    verdict: Verdict
    category: RefusalCategory | None = None
    #: i18n code under `server.chat.*`. Never English prose from here.
    code: str = ""
    matched: str = ""
    """The term that triggered a refusal. Logged, and useful in tests."""


# ---------------------------------------------------------------- vocabulary
#
# Deliberately broad. A false refusal costs a farmer one unanswered question;
# a false allowance can cost them a spraying accident. Where the two errors are
# that asymmetric, over-refusing is the correct bias.

_CHEMICALS = [
    # English
    "pesticide", "insecticide", "fungicide", "herbicide", "weedicide",
    "spray", "spraying", "dose", "dosage", "ml per", "gram per", "kg per acre",
    "urea", "dap", "npk", "fertiliser", "fertilizer", "manure dose",
    "glyphosate", "imidacloprid", "chlorpyrifos", "mancozeb", "carbendazim",
    "monocrotophos", "paraquat", "atrazine",
    # Hindi
    "कीटनाशक", "खरपतवारनाशक", "फफूंदनाशक", "छिड़काव", "छिड़कना",
    "यूरिया", "डीएपी", "खाद कितनी", "दवा", "दवाई", "स्प्रे", "मात्रा",
]

_DIAGNOSIS = [
    "yellow leaves", "leaves are turning", "leaf spot", "wilting", "wilt",
    "my crop has", "my plants are", "disease", "infected", "infestation",
    "pest attack", "rot", "blight", "rust on", "curling",
    "पत्ते पीले", "पत्ती पीली", "बीमारी", "रोग", "कीड़े लग", "सड़ रह",
    "मुरझा", "धब्बे",
]

_FINANCE = [
    "loan", "credit", "kisan credit card", "kcc", "mortgage", "interest rate",
    "insurance claim", "subsidy eligib", "am i eligible", "how do i apply",
    "bank will give", "emi", "repay",
    "ऋण", "कर्ज", "कर्ज़", "लोन", "ब्याज", "बीमा क्लेम", "सब्सिडी मिलेगी",
    "पात्र हूं", "पात्र हूँ",
]

_MEDICAL = [
    "my health", "i feel sick", "poisoning", "swallowed", "inhaled",
    "doctor", "hospital", "my cow", "my buffalo", "cattle disease",
    "बीमार हूं", "बीमार हूँ", "ज़हर", "जहर", "डॉक्टर", "अस्पताल",
    "मेरी गाय", "मेरी भैंस",
]

#: Asking about a crop or place the advisory does not cover. Weaker signal, so
#: this is checked last and only on explicit phrasings.
_OTHER_FIELD = [
    "my other field", "another field", "different village", "my brother's",
    "दूसरा खेत", "दूसरे खेत", "दूसरे गांव", "दूसरे गाँव",
]

_CATEGORIES: list[tuple[RefusalCategory, list[str]]] = [
    ("medical", _MEDICAL),
    ("chemicals", _CHEMICALS),
    ("diagnosis", _DIAGNOSIS),
    ("finance", _FINANCE),
    ("other_field", _OTHER_FIELD),
]


def _fold(text: str) -> str:
    """Case and width folding, shared by both normalisations.

    NFKC matters more than it looks: it collapses full-width Latin and several
    Devanagari presentation forms, which is the cheapest way to stop a term
    being smuggled past a substring check by typing it differently.
    """
    return unicodedata.normalize("NFKC", text).casefold()


_SEPARATORS = r"[\s\-_.,;:!?/\\|]+"


def _spaced(text: str) -> str:
    """Separators become single spaces. Keeps multi-word terms matchable."""
    return re.sub(_SEPARATORS, " ", _fold(text)).strip()


def _tight(text: str) -> str:
    """Separators removed entirely. Catches words broken up on purpose.

    Both forms are needed and neither is sufficient. Collapsing "pest-icide"
    to a space gives "pest icide", which does NOT contain "pesticide" — the
    normalisation intended to defeat the trick was performing it. Removing
    separators fixes that but destroys "kg per acre". So terms are tested
    against both strings and a hit in either is a hit.
    """
    return re.sub(_SEPARATORS, "", _fold(text))


def _normalise(text: str) -> str:
    """Kept for callers that want the readable form."""
    return _spaced(text)


def classify(message: str) -> ScopeDecision:
    """Decide whether the chat may answer this at all.

    Runs before any model call, so a refusal costs nothing and cannot fail
    open when an API is down.
    """
    spaced, tight = _spaced(message), _tight(message)
    if not spaced:
        return ScopeDecision(verdict="refused", category=None, code="empty")

    for category, terms in _CATEGORIES:
        for term in terms:
            if _spaced(term) in spaced or _tight(term) in tight:
                return ScopeDecision(
                    verdict="refused",
                    category=category,
                    code=f"refuse_{category}",
                    matched=term,
                )

    return ScopeDecision(verdict="allowed")
