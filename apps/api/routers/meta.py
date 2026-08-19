"""Reference lists for the client's dropdowns. Cached hard on both sides."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

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
                names=crop.names,
                category=crop.category,
                seasons=list(crop.seasons),
            )
            for crop in reference.crops.values()
        ]
    )


@router.get("/msp", response_model=api.MspResponse)
def msp() -> api.MspResponse:
    """The Minimum Support Price lookup table.

    Static reference data read straight off disk. No computation and no
    request-dependent behaviour — it is the same table for every caller, which
    is why it is cached at module level rather than reloaded per request.
    """
    return _msp_table()


@lru_cache(maxsize=1)
def _msp_table() -> api.MspResponse:
    import yaml

    path = Path(__file__).resolve().parents[3] / "data" / "reference" / "msp.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    # PyYAML parses bare ISO dates into `date` objects, which do not satisfy a
    # `str` field. Stringifying here rather than widening the schema: the wire
    # format for this is a date string, and loosening the contract to
    # accommodate a parser quirk would be the wrong direction.
    sources = {
        key: {**value, "published": str(value["published"])}
        for key, value in raw["sources"].items()
    }
    return api.MspResponse(
        marketing_season=str(raw["marketing_season"]),
        updated=str(raw["updated"]),
        crops=raw["crops"],
        sources=sources,
        not_listed_here=raw.get("not_listed_here") or [],
    )
