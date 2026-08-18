"""Recent mandi prices for one crop.

Live Agmarknet integration is not built yet. Rather than invent a series, this
returns an empty one with the source stated - a chart with no points is honest;
a chart with made-up points is not.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from apps.api.core import errors
from apps.api.core.reference import ReferenceData
from apps.api.routers.deps import get_reference
from apps.api.schemas import contract as api

router = APIRouter(prefix="/api/v1/prices", tags=["prices"])


@router.get("/{crop_code}", response_model=api.PricesResponse)
def prices(
    crop_code: str,
    district_code: str | None = None,
    days: int = Query(default=90, ge=1, le=365),
    reference: ReferenceData = Depends(get_reference),
) -> api.PricesResponse:
    crop = reference.crops.get(crop_code.upper())
    if crop is None:
        raise errors.NotFound(f"Unknown crop_code: {crop_code!r}", field="crop_code")

    econ = reference.economics_raw.get(crop.crop_code, {})
    source = reference.source_for(econ.get("price_source"))

    return api.PricesResponse(
        crop_code=crop.crop_code,
        unit="per_quintal",
        series=[],
        source=(
            source.citation
            if source
            else "No price series available for this crop yet (Agmarknet integration pending)."
        ),
        fetched_at=datetime.now(timezone.utc),
    )
