"""Conditions without ranking.

Called as soon as the farmer picks a location, so there is something on screen
while the full recommendation runs. Target p95 is 2s, against 4s for the main
endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter

from apps.api.schemas import contract as api
from apps.api.services.recommendation_service import build_field_summary, build_indices

router = APIRouter(prefix="/api/v1/geo", tags=["geo"])


@router.post("/field-summary", response_model=api.FieldSummaryResponse)
def field_summary(request: api.FieldSummaryRequest) -> api.FieldSummaryResponse:
    return build_field_summary(request.location)


@router.post("/indices", response_model=api.IndicesResponse)
def indices(request: api.IndicesRequest) -> api.IndicesResponse:
    """Sentinel-2 indices for the drawn or selected field.

    Separate from /field-summary because the map calls it on every boundary
    edit, while field-summary is only needed once per location.
    """
    return build_indices(request.location)
