"""Farmer Q&A about a stored advisory.

The advisory is fetched by `request_id` server-side rather than accepted from
the client. A client that could post its own grounding document could put
anything in it, and the model would faithfully answer from the fiction —
turning the one component with a hallucination surface into a machine for
laundering made-up numbers through a trusted-looking interface.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from apps.api.core import errors
from apps.api.core.config import get_settings
from apps.api.core.repository import ResultRepository
from apps.api.routers.deps import get_repository
from apps.api.schemas import contract as api
from apps.api.services.chat import answer
from apps.api.services.llm_client import build_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/recommendations", tags=["chat"])


@router.post("/{request_id}/chat", response_model=api.ChatResponse)
def ask(
    request_id: str,
    body: api.ChatRequest,
    repository: ResultRepository = Depends(get_repository),
) -> api.ChatResponse:
    payload = repository.get(request_id)
    if payload is None:
        # Same 404 as fetching the advisory itself. A chat about an expired
        # result would be a chat about nothing.
        raise errors.NotFound(f"No advisory found for {request_id}.")

    settings = get_settings()

    if body.turn > settings.chat_max_turns:
        # RateLimited carries 429. ai-design.md §8 names CHAT_LIMIT_REACHED as
        # a distinct code; it maps onto the existing envelope rather than
        # introducing a second error shape.
        raise errors.RateLimited(
            f"This conversation has reached its limit of "
            f"{settings.chat_max_turns} questions."
        )

    result = answer(body.message, payload, call_model=build_client(settings))

    return api.ChatResponse(
        source=result.source,
        code=result.code,
        params=result.params,
        text=result.text,
        refusal_category=result.refusal_category,
    )
