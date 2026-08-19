"""Whether a crop is a sensible thing to plant after the last one.

WHY THIS IS ASKED RATHER THAN INFERRED
--------------------------------------
The satellite can see that a crop was grown and roughly when. It cannot see
WHICH crop, and rotation logic is entirely about which — wheat after wheat is a
disease problem, wheat after chickpea is free nitrogen, and the NDVI curve for
the two is indistinguishable.

So the farmer is asked, in one dropdown they can skip. One question answered
beats a whole model guessing.

WHAT THE RULES ARE, AND WHERE THEY COME FROM
--------------------------------------------
Four mechanisms, each a thing an agronomist would say out loud:

  same crop again      Soil-borne pathogens and specialised pests accumulate
                       with nothing to break their cycle, and the same rooting
                       depth mines the same layer twice.

  same plant family    Relatives share pathogens. Wheat and barley share the
                       rusts; potato shares blight with every other
                       solanaceous crop. Different crop, same disease.

  a legume in the      Legumes fix nitrogen and leave a usable residue behind
  sequence             them. Following one is the single cheapest fertility
                       gain available; preceding one breaks a cereal disease
                       cycle.

  two heavy feeders    Back-to-back high-nitrogen crops draw the same account
  in a row             down twice with nothing paid in.

Plus one check that uses data already in the reference tables: if both crops
name the same pest or disease in `risks`, that is a carryover risk regardless
of what family they belong to.

STATUS OF THESE NUMBERS
-----------------------
The scores below are expert-set, not fitted to yield data, and carry the same
provisional flag as the rest of the agronomy. They encode ordering — legume to
cereal beats cereal to cereal beats the same cereal twice — which is not
controversial. The exact gaps between them are a judgement call awaiting the
same review as crops.yaml.
"""

from __future__ import annotations

from services.ml.types import CropSpec

# --------------------------------------------------------------------- scores

#: The same crop in the same ground, back to back. Every mechanism at once.
SAME_CROP = 0.10

#: A relative: different crop, shared pathogens.
SAME_FAMILY = 0.30

#: Different family, but they name the same pest or disease between them.
SHARED_PEST = 0.35

#: Two high-nitrogen crops in sequence with nothing fixing any.
BOTH_HEAVY_FEEDERS = 0.45

#: An unrelated crop after an unrelated crop. Fine, unremarkable.
CLEAN_BREAK = 0.75

#: Following a legume. The residue is real and free.
AFTER_LEGUME = 1.00

#: Planting a legume after something else. Breaks the cycle and feeds itself.
LEGUME_NEXT = 0.90


def _shared_risk(previous: CropSpec, candidate: CropSpec) -> str | None:
    """A pest or disease both crops carry, by name.

    Uses the risk names already in crops.yaml rather than a second table, so
    the sentence the farmer reads names something they can look up.
    """
    biological = {"pest", "disease"}
    previous_names = {
        risk.name.lower() for risk in previous.risks if risk.type in biological
    }
    for risk in candidate.risks:
        if risk.type in biological and risk.name.lower() in previous_names:
            return risk.name
    return None


def score(previous: CropSpec | None, candidate: CropSpec) -> tuple[float | None, str, dict]:
    """(0..1, message code, params). None means the question was not asked.

    A None score is not a bad score. The farmer skipped an optional dropdown;
    that is a gap in what we were told, not a fault in the field, and the
    ranker drops the weight rather than penalising the crop.
    """
    if previous is None:
        return None, "rotation_unknown", {}

    if previous.crop_code == candidate.crop_code:
        return (
            SAME_CROP,
            "rotation_same_crop",
            {"crop": candidate.name.lower(), "crop_code": candidate.crop_code},
        )

    # A legume behind you is the best thing that can be behind you.
    if previous.legume and not candidate.legume:
        return (
            AFTER_LEGUME,
            "rotation_after_legume",
            {
                "previous": previous.name.lower(),
                "previous_code": previous.crop_code,
                "crop": candidate.name.lower(),
                "crop_code": candidate.crop_code,
            },
        )

    shared = _shared_risk(previous, candidate)

    if previous.family and previous.family == candidate.family:
        return (
            SAME_FAMILY,
            "rotation_same_family_pest" if shared else "rotation_same_family",
            {
                "previous": previous.name.lower(),
                "previous_code": previous.crop_code,
                "crop": candidate.name.lower(),
                "crop_code": candidate.crop_code,
                "pest": shared or "",
            },
        )

    if shared:
        return (
            SHARED_PEST,
            "rotation_shared_pest",
            {
                "previous": previous.name.lower(),
                "previous_code": previous.crop_code,
                "pest": shared,
            },
        )

    if candidate.legume:
        return (
            LEGUME_NEXT,
            "rotation_legume_next",
            {
                "crop": candidate.name.lower(),
                "crop_code": candidate.crop_code,
                "previous": previous.name.lower(),
                "previous_code": previous.crop_code,
            },
        )

    if previous.nitrogen_demand == "high" and candidate.nitrogen_demand == "high":
        return (
            BOTH_HEAVY_FEEDERS,
            "rotation_both_hungry",
            {
                "previous": previous.name.lower(),
                "previous_code": previous.crop_code,
                "crop": candidate.name.lower(),
                "crop_code": candidate.crop_code,
            },
        )

    return (
        CLEAN_BREAK,
        "rotation_clean_break",
        {
            "previous": previous.name.lower(),
            "previous_code": previous.crop_code,
            "crop": candidate.name.lower(),
            "crop_code": candidate.crop_code,
        },
    )
