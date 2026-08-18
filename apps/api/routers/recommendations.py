"""The core endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from apps.api.core import errors
from apps.api.core.reference import ReferenceData
from apps.api.core.repository import ResultRepository
from apps.api.routers.deps import get_reference, get_repository, get_request_id
from apps.api.schemas import contract as api
from apps.api.services.recommendation_service import recommend

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


@router.post("", response_model=api.RecommendationResponse)
def create(
    request: api.RecommendationRequest,
    reference: ReferenceData = Depends(get_reference),
    repository: ResultRepository = Depends(get_repository),
    request_id: str = Depends(get_request_id),
) -> api.RecommendationResponse:
    result = recommend(request, reference, request_id=request_id)

    # Persist for the replay window. A failure here is logged, not raised - the
    # answer is already computed and the farmer should still get it.
    repository.save(result.request_id, result.model_dump(mode="json"))
    return result


@router.get("/{request_id}", response_model=api.RecommendationResponse)
def replay(
    request_id: str,
    repository: ResultRepository = Depends(get_repository),
) -> api.RecommendationResponse:
    payload = repository.get(request_id)
    if payload is None:
        raise errors.NotFound(
            "That result has expired or never existed. Results are kept for 30 days.",
            field="request_id",
        )
    return api.RecommendationResponse.model_validate(payload)
