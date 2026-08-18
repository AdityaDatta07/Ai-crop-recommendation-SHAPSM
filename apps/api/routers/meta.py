"""Reference lists for the client's dropdowns. Cached hard on both sides."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from apps.api.core.reference import ReferenceData
from apps.api.routers.deps import get_reference
from apps.api.schemas import contract as api

router = APIRouter(prefix="/api/v1/meta", tags=["meta"])

# These change on the order of never. Let the browser keep them for a day.
CACHE_HEADER = "public, max-age=86400"


@router.get("/districts", response_model=api.DistrictsResponse)
def districts(
    response: Response,
    state_code: str | None = None,
    reference: ReferenceData = Depends(get_reference),
) -> api.DistrictsResponse:
    states = reference.districts["states"]
    if state_code:
        states = [state for state in states if state["state_code"] == state_code.upper()]

    response.headers["Cache-Control"] = CACHE_HEADER
    return api.DistrictsResponse(states=states)


@router.get("/crops", response_model=api.CropsResponse)
def crops(
    response: Response,
    reference: ReferenceData = Depends(get_reference),
) -> api.CropsResponse:
    response.headers["Cache-Control"] = CACHE_HEADER
    return api.CropsResponse(
        crops=[
            api.Crop(
                crop_code=crop.crop_code,
                name=crop.name,
                name_hi=crop.name_hi,
                category=crop.category,
                seasons=list(crop.seasons),
            )
            for crop in reference.crops.values()
        ]
    )
