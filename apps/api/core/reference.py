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
#: Crop names in every language the app speaks.
#
# Kept here rather than in the frontend dictionaries because these come from
# the same reference data the ranker uses — one list of crops, not two. The
# API serves the whole `names` map and the client picks its locale, so adding
# a language never means touching two places and getting one of them wrong.
#
# NOT REVIEWED BY NATIVE SPEAKERS. Crop names are the easiest thing here to
# get subtly wrong: several have regional variants, and the common name in one
# district is a different plant in another. Flagged in docs/handover.md.
CROP_NAMES: dict[str, dict[str, str]] = {
    "WHEAT":     {"en": "Wheat",        "hi": "गेहूँ",     "mr": "गहू",       "bn": "গম",        "gu": "ઘઉં",       "ta": "கோதுமை",   "te": "గోధుమ"},
    "RICE":      {"en": "Rice",         "hi": "चावल",      "mr": "भात",       "bn": "ধান",       "gu": "ડાંગર",     "ta": "நெல்",     "te": "వరి"},
    "MAIZE":     {"en": "Maize",        "hi": "मक्का",     "mr": "मका",       "bn": "ভুট্টা",     "gu": "મકાઈ",      "ta": "மக்காச்சோளம்", "te": "మొక్కజొన్న"},
    "BARLEY":    {"en": "Barley",       "hi": "जौ",        "mr": "सातू",      "bn": "যব",        "gu": "જવ",        "ta": "பார்லி",   "te": "బార్లీ"},
    "SORGHUM":   {"en": "Sorghum",      "hi": "ज्वार",     "mr": "ज्वारी",    "bn": "জোয়ার",    "gu": "જુવાર",     "ta": "சோளம்",    "te": "జొన్న"},
    "PEARLMLT":  {"en": "Pearl millet", "hi": "बाजरा",     "mr": "बाजरी",     "bn": "বাজরা",     "gu": "બાજરી",     "ta": "கம்பு",    "te": "సజ్జ"},
    "CHICKPEA":  {"en": "Chickpea",     "hi": "चना",       "mr": "हरभरा",     "bn": "ছোলা",      "gu": "ચણા",       "ta": "கொண்டைக்கடலை", "te": "శనగ"},
    "PIGEONPEA": {"en": "Pigeon pea",   "hi": "अरहर",      "mr": "तूर",       "bn": "অড়হর",     "gu": "તુવેર",     "ta": "துவரை",    "te": "కంది"},
    "LENTIL":    {"en": "Lentil",       "hi": "मसूर",      "mr": "मसूर",      "bn": "মসুর",      "gu": "મસૂર",      "ta": "மைசூர் பருப்பு", "te": "మసూర్"},
    "MUSTARD":   {"en": "Mustard",      "hi": "सरसों",     "mr": "मोहरी",     "bn": "সরিষা",     "gu": "રાઈ",       "ta": "கடுகு",    "te": "ఆవాలు"},
    "GROUNDNUT": {"en": "Groundnut",    "hi": "मूंगफली",   "mr": "भुईमूग",    "bn": "চিনাবাদাম", "gu": "મગફળી",     "ta": "நிலக்கடலை", "te": "వేరుశనగ"},
    "SOYBEAN":   {"en": "Soybean",      "hi": "सोयाबीन",   "mr": "सोयाबीन",   "bn": "সয়াবিন",   "gu": "સોયાબીન",   "ta": "சோயாபீன்", "te": "సోయాబీన్"},
    "COTTON":    {"en": "Cotton",       "hi": "कपास",      "mr": "कापूस",     "bn": "তুলা",      "gu": "કપાસ",      "ta": "பருத்தி",  "te": "పత్తి"},
    "SUGARCANE": {"en": "Sugarcane",    "hi": "गन्ना",     "mr": "ऊस",        "bn": "আখ",        "gu": "શેરડી",     "ta": "கரும்பு",  "te": "చెరకు"},
    "POTATO":    {"en": "Potato",       "hi": "आलू",       "mr": "बटाटा",     "bn": "আলু",       "gu": "બટાટા",     "ta": "உருளைக்கிழங்கு", "te": "బంగాళదుంప"},
    "ONION":     {"en": "Onion",        "hi": "प्याज",     "mr": "कांदा",     "bn": "পেঁয়াজ",    "gu": "ડુંગળી",    "ta": "வெங்காயம்", "te": "ఉల్లిపాయ"},
}

CROP_CATEGORIES: dict[str, str] = {
    "WHEAT": "cereal", "RICE": "cereal", "MAIZE": "cereal", "BARLEY": "cereal",
    "SORGHUM": "millet", "PEARLMLT": "millet",
    "CHICKPEA": "pulse", "PIGEONPEA": "pulse", "LENTIL": "pulse",
    "MUSTARD": "oilseed", "GROUNDNUT": "oilseed", "SOYBEAN": "oilseed",
    "COTTON": "fibre", "SUGARCANE": "cash",
    "POTATO": "vegetable", "ONION": "vegetable",
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

        names = CROP_NAMES.get(code, {"en": code.title()})
        name = names.get("en", code.title())
        category = CROP_CATEGORIES.get(code, "other")

        crops[code] = CropSpec(
            crop_code=code,
            name=name,
            name_hi=names.get("hi") or None,
            names=names,
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
            family=str(spec.get("family", "")),
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
