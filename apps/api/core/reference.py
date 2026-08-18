"""Loads data/reference at startup.

This module is the single owner of the reference files. services/ml receives
CropSpec objects as arguments rather than reading YAML itself, which keeps the
ranker a pure function of its inputs and testable without a filesystem.

Provenance is enforced here: every `*_source` key must resolve to an entry in
sources.yaml, or startup fails. A number without a source is a bug, not a
warning - architecture.md principle 5.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from services.ml.types import CropSpec, DateWindow, Risk

logger = logging.getLogger(__name__)

REFERENCE_DIR = Path(__file__).resolve().parents[3] / "data" / "reference"

# Display names. crop_code is the stable join key and is never shown.
CROP_NAMES: dict[str, tuple[str, str, str]] = {
    # code: (English name, Hindi name, category)
    "WHEAT": ("Wheat", "गेहूँ", "cereal"),
    "RICE": ("Rice", "चावल", "cereal"),
    "MAIZE": ("Maize", "मक्का", "cereal"),
    "BARLEY": ("Barley", "जौ", "cereal"),
    "SORGHUM": ("Sorghum", "ज्वार", "millet"),
    "PEARLMLT": ("Pearl millet", "बाजरा", "millet"),
    "CHICKPEA": ("Chickpea", "चना", "pulse"),
    "PIGEONPEA": ("Pigeon pea", "अरहर", "pulse"),
    "LENTIL": ("Lentil", "मसूर", "pulse"),
    "MUSTARD": ("Mustard", "सरसों", "oilseed"),
    "GROUNDNUT": ("Groundnut", "मूंगफली", "oilseed"),
    "SOYBEAN": ("Soybean", "सोयाबीन", "oilseed"),
    "COTTON": ("Cotton", "कपास", "fibre"),
    "SUGARCANE": ("Sugarcane", "गन्ना", "cash"),
    "POTATO": ("Potato", "आलू", "vegetable"),
    "ONION": ("Onion", "प्याज", "vegetable"),
}


class ReferenceDataError(RuntimeError):
    """Raised at startup when the reference data is internally inconsistent."""


@dataclass(frozen=True)
class Source:
    key: str
    tier: str
    citation: str
    caveat: str | None
    url: str | None

    @property
    def is_provisional(self) -> bool:
        return self.tier != "cited"


@dataclass(frozen=True)
class ReferenceData:
    crops: dict[str, CropSpec]
    sources: dict[str, Source]
    districts: dict
    economics_raw: dict
    agronomy_source_key: str

    def crops_for_season(self, season: str) -> list[CropSpec]:
        return [crop for crop in self.crops.values() if season in crop.seasons]

    def source_for(self, key: str | None) -> Source | None:
        return self.sources.get(key) if key else None

    @property
    def agronomy_source(self) -> Source:
        return self.sources[self.agronomy_source_key]


def _read_yaml(name: str) -> dict:
    with (REFERENCE_DIR / name).open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


@lru_cache(maxsize=1)
def load_reference() -> ReferenceData:
    crops_doc = _read_yaml("crops.yaml")
    economics_doc = _read_yaml("economics.yaml")
    sources_doc = _read_yaml("sources.yaml")

    with (REFERENCE_DIR / "districts.json").open(encoding="utf-8") as handle:
        districts = json.load(handle)

    sources = {
        key: Source(
            key=key,
            tier=spec.get("tier", "provisional"),
            citation=spec.get("citation", key),
            caveat=spec.get("caveat"),
            url=spec.get("url"),
        )
        for key, spec in sources_doc["sources"].items()
    }

    agronomy_key = crops_doc.get("source")
    if agronomy_key not in sources:
        raise ReferenceDataError(
            f"crops.yaml declares source {agronomy_key!r}, which is not in sources.yaml"
        )

    crop_specs = crops_doc["crops"]
    econ_specs = economics_doc["crops"]

    missing = set(crop_specs) ^ set(econ_specs)
    if missing:
        raise ReferenceDataError(
            f"crops.yaml and economics.yaml disagree on which crops exist: {sorted(missing)}"
        )

    crops: dict[str, CropSpec] = {}
    for code, spec in crop_specs.items():
        econ = econ_specs[code]

        # Provenance check. A price without a source is the exact failure this
        # project cannot afford in front of a judge.
        for value_key, source_key in (
            ("price_per_quintal", "price_source"),
            ("cost_a2fl_per_quintal", "cost_source"),
            ("yield_kg_per_ha", "yield_source"),
        ):
            if econ.get(value_key) is not None and econ.get(source_key) not in sources:
                raise ReferenceDataError(
                    f"{code}.{value_key} has no resolvable source "
                    f"(got {econ.get(source_key)!r})"
                )

        name, name_hi, category = CROP_NAMES.get(code, (code.title(), "", "other"))

        crops[code] = CropSpec(
            crop_code=code,
            name=name,
            name_hi=name_hi or None,
            category=category,
            seasons=tuple(spec["seasons"]),
            ph_optimal=tuple(spec["ph_optimal"]),
            ph_absolute=tuple(spec["ph_absolute"]),
            temp_optimal_c=tuple(spec["temp_optimal_c"]),
            temp_absolute_c=tuple(spec["temp_absolute_c"]),
            rainfall_mm=tuple(spec["rainfall_mm"]),
            irrigation_need=spec["irrigation_need"],
            texture_preferred=tuple(spec["texture_preferred"]),
            nitrogen_demand=spec["nitrogen_demand"],
            legume=bool(spec["legume"]),
            duration_days=int(spec["duration_days"]),
            sowing_window=DateWindow(**spec["sowing_window"]),
            varieties=tuple(spec.get("varieties", ())),
            risks=tuple(Risk(**risk) for risk in spec.get("risks", ())),
            price_per_quintal=econ.get("price_per_quintal"),
            cost_a2fl_per_quintal=econ.get("cost_a2fl_per_quintal"),
            yield_kg_per_ha=econ.get("yield_kg_per_ha"),
        )

    logger.info(
        "Loaded %d crops, %d sources, %d states from %s",
        len(crops),
        len(sources),
        len(districts["states"]),
        REFERENCE_DIR,
    )
    return ReferenceData(
        crops=crops,
        sources=sources,
        districts=districts,
        economics_raw=econ_specs,
        agronomy_source_key=agronomy_key,
    )
