"""Minimal LLM client. One method, three providers, no SDK.

WHY NO SDK
----------
Each vendor SDK is tens of megabytes of dependency for one HTTP POST, and each
brings its own transitive versions of httpx and pydantic into a project that
already pins both. The request bodies below are small enough to read in full,
which also means the grounding document is visibly the only thing sent.

WHY THE PROVIDER IS SWAPPABLE
-----------------------------
ai-design.md §3.1 calls a provider outage on demo day a real risk worth
designing around, and it is right: this is a hackathon build with one key and
no fallback billing. Switching provider is an .env change, not a code change.

WHAT LEAVES THE MACHINE
-----------------------
The system prompt, the farmer's question, and the grounding document — which is
one advisory: district, area, season, conditions, five crops, warnings. No
personal identifiers are collected anywhere in this app, so none can be sent.
"""

from __future__ import annotations

import json
import logging

import httpx

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 20.0

SYSTEM_PROMPT = """\
You are an assistant helping an Indian farmer understand a crop recommendation
they have just received. You are not a general agriculture advisor.

RULES:
1. Answer ONLY from the grounding document below. If the answer is not there,
   say you do not have that information.
2. Never state a number that is not in the grounding document.
3. REFUSE and redirect to the local Krishi Vigyan Kendra or district
   agriculture extension officer for: pesticide, herbicide or fungicide
   selection or dosage; fertiliser quantities beyond what the document states;
   plant disease or pest diagnosis; loans, credit, insurance or subsidy
   eligibility; medical or veterinary questions; any crop or field not in the
   grounding document.
4. Never contradict the ranking. If asked to justify a different crop, explain
   what the scoring found. Do not argue the farmer into or out of a decision.
5. Do not speculate about weather, prices or policy beyond the document.
6. Reply in the language of the question. Keep answers under 100 words.
7. If the farmer is distressed about money or crop failure, respond with care,
   acknowledge the difficulty, and point them to their local extension office.
   Do not offer financial or emotional counselling.

TONE: respectful and practical. Never condescending. The farmer knows their
land better than you do.

GROUNDING DOCUMENT — everything you know:
{document}
"""


class LLMClient:
    def __init__(self, provider: str, model: str, api_key: str, max_tokens: int = 2048) -> None:
        self.provider = provider.lower().strip()
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens

    def __call__(self, message: str, document: dict) -> str:
        prompt = SYSTEM_PROMPT.format(document=json.dumps(document, ensure_ascii=False, default=str))
        if self.provider == "gemini":
            return self._gemini(prompt, message)
        if self.provider == "anthropic":
            return self._anthropic(prompt, message)
        if self.provider == "openai":
            return self._openai(prompt, message)
        raise ValueError(f"Unknown LLM_PROVIDER {self.provider!r}")

    # ------------------------------------------------------------ providers

    def _gemini(self, system: str, message: str) -> str:
        # The key goes in a header, not the query string. In the URL it would
        # land in every proxy log and browser history between here and Google.
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self.api_key, "content-type": "application/json"},
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": message}]}],
                "generationConfig": {"maxOutputTokens": self.max_tokens, "temperature": 0.2},
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts") or []
        return "".join(part.get("text", "") for part in parts)

    def _anthropic(self, system: str, message: str) -> str:
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": self.max_tokens,
                "temperature": 0.2,
                "system": system,
                "messages": [{"role": "user", "content": message}],
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        blocks = response.json().get("content") or []
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")

    def _openai(self, system: str, message: str) -> str:
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "authorization": f"Bearer {self.api_key}",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": self.max_tokens,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": message},
                ],
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        choices = response.json().get("choices") or [{}]
        return choices[0].get("message", {}).get("content", "")


def build_client(settings) -> LLMClient | None:
    """None when unconfigured, which the chat treats as "use templates only"."""
    if not settings.llm_configured:
        logger.info("No LLM key configured; chat will answer from templates only")
        return None
    return LLMClient(
        provider=settings.llm_provider,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        max_tokens=settings.llm_max_tokens,
    )
