# Data Sources

**Version:** 1.0 · **Last updated:** 2026-08-16
Companion documents: [`architecture.md`](./architecture.md) · [`api-contract.md`](./api-contract.md)

Every number the system shows a farmer originates from one of the sources below. If a figure cannot be traced to a row in this document, it must not appear in the UI.

**Verification status is stated per source.** Rows marked ⚠️ need confirmation by the team before the submission — do not present them to judges as settled.

---

## 1. Summary

| # | Source | Provides | Licence | Verified |
|---|---|---|---|---|
| 1 | ISRIC SoilGrids 250m v2.0 | Soil pH, texture, organic carbon, nitrogen | CC BY 4.0 | ✅ |
| 2 | Copernicus Sentinel-2 (L2A) | NDVI, current vegetation state | Copernicus Sentinel Data Terms | ✅ |
| 3 | CHIRPS v2.0 / v3.0 | Rainfall, 1981–present, 0.05° | Public domain (CC0) | ✅ |
| 4 | IMD gridded rainfall 0.25° | Indian rainfall normals, 1901–2024 | ⚠️ Not stated publicly | ⚠️ |
| 5 | Agmarknet via data.gov.in | Daily mandi min/max/modal prices | GODL-India | ✅ |
| 6 | DES Cost of Cultivation | Input costs per crop per state | ⚠️ Publication terms | ⚠️ |
| 7 | Soil Health Card portal | District nutrient status | ⚠️ No documented API | ⚠️ |
| 8 | ICAR package of practices | Crop calendars, agronomic thresholds | ⚠️ Per-publication | ⚠️ |
| 9 | Survey of India / GADM boundaries | District boundaries | ⚠️ Varies by source | ⚠️ |

**Attribution obligations:** sources 1 and 5 both require a visible attribution statement. See section 4.

### 1.1 The platform licence, separate from the data licences ✅

Earth Engine's own terms are distinct from the terms of the datasets inside it, and this catches teams out.

> Earth Engine is **free to use for research, education, and nonprofit use.** Commercial and government use requires a paid Google Cloud subscription.

An SIH submission is educational use, so we are within the free tier. But this constrains the honest answer to *"how would you scale this?"* — the answer is that a production deployment serving farmers commercially would need a commercial Earth Engine plan, or a migration to a self-hosted raster stack. Say this rather than claim the architecture scales for free.

Register at `console.cloud.google.com/earth-engine`.

---

## 2. Source detail

### 2.1 ISRIC SoilGrids 250m v2.0 ✅

Primary soil input. Global machine-learning soil property maps trained on the WoSIS profile database.

| Field | Value |
|---|---|
| Provider | ISRIC — World Soil Information |
| GEE asset | `ISRIC/SoilGrids250m/v2_0` (community-contributed) |
| Access | Earth Engine, `services/geo` |
| Resolution | 250 m |
| Depths | 0–5, 5–15, 15–30, 30–60, 60–100, 100–200 cm — we use 0–30 cm |
| Properties used | pH (H₂O), sand/silt/clay, organic carbon, total nitrogen |
| Licence | **CC BY 4.0** |
| Refresh | Static; v2.0 |

**Attribution required.** Standard form: *"Soil data © ISRIC — World Soil Information, SoilGrids250m v2.0, CC BY 4.0."*

**Limitation to state honestly:** SoilGrids is a *model prediction* at 250 m, not a measurement of the farmer's field. Reported uncertainty is substantial for micronutrients. We use it for pH, texture and organic carbon — the properties it predicts most reliably — and treat NPK as indicative only.

Note the layers are contributed to the GEE catalog by ISRIC rather than being a Google-curated dataset; confirm the asset ID resolves before demo day.

### 2.2 Copernicus Sentinel-2 Level-2A ✅

Current vegetation state, used for NDVI and to detect whether a field is already cropped.

| Field | Value |
|---|---|
| Provider | European Union / ESA / Copernicus |
| GEE asset | `COPERNICUS/S2_SR_HARMONIZED` |
| Coverage | 2017-03-28 onward (2017–2018 L2 coverage is **not** global) |
| Revisit | 5 days |
| Resolution | 10 m for B4 and B8; 20 m for SCL and `MSK_CLDPRB` |
| Bands used | B4 (red, 664.5 nm), B8 (NIR, 835.1 nm) for NDVI; SCL / `MSK_CLDPRB` for cloud masking |
| Scaling | Reflectance scale factor 0.0001 — divide by 10000 |
| Licence | Copernicus Sentinel Data Terms and Conditions |
| Refresh | Continuous |

**Implementation notes, all verified against the catalog page.**

- Divide by 10000 before computing NDVI. Forgetting this produces NDVI values that look plausible but are wrong.
- Use `_HARMONIZED`, not the legacy `COPERNICUS/S2_SR`. After 2022-01-25, scenes with processing baseline 04.00+ have their values shifted by 1000; the harmonized collection corrects this. Mixing them silently corrupts any multi-year comparison.
- **The QA60 cloud-masking example in Google's own documentation has a trap:** QA60 is masked out for scenes between 2022-01-25 and 2024-02-28. Copy-pasting the standard `maskS2clouds` function will silently return empty results for that period. Prefer the `SCL` band (classes 3, 8, 9, 10 are shadow and cloud) or `MSK_CLDPRB`, or use `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED`.
- Cloud masking is mandatory over India. Use a median composite over a trailing 30–60 day window, never a single scene — a kharif-season single scene will usually be cloud.

### 2.3 CHIRPS rainfall ✅

Satellite-plus-station rainfall, used for historical rainfall context and season totals.

| Field | Value |
|---|---|
| Provider | Climate Hazards Center, UC Santa Barbara |
| GEE asset | `UCSB-CHG/CHIRPS/DAILY` (v2.0 Final) |
| Alternative | `UCSB-CHC/CHIRPS/V3/DAILY_SAT` (v3.0, IMERG-based, near-real-time) |
| Coverage | 1981–present, 50°N–50°S (v2) / 60°N–60°S (v3) |
| Resolution | 0.05° (~5.5 km) |
| Licence | **Public domain (CC0)** — rights waived by the Climate Hazards Center |
| Refresh | v2 Final has a lag of several weeks; v3 near-real-time is faster but preliminary |

**Recommendation for v1:** use CHIRPS as the primary rainfall source rather than IMD. It is in Earth Engine already, unambiguously licensed, and requires no separate download pipeline. Reserve IMD for validation.

### 2.4 IMD gridded rainfall ⚠️

Indian Meteorological Department 0.25° daily gridded rainfall, 1901–2024. Higher credibility with Indian judges than a US-produced dataset.

| Field | Value |
|---|---|
| Provider | India Meteorological Department, Pune |
| Access | Manual download from imdpune.gov.in, NetCDF or binary |
| Resolution | 0.25° (~27 km), 135 × 129 grid, origin 6.5°N 66.5°E |
| Coverage | 1901–2024 |
| Licence | **⚠️ Not published on the download pages.** Must be confirmed. |
| Refresh | Annual for the archive; separate real-time product exists |

**Action required.** IMD does not state licence terms on the gridded data download pages. Before relying on this in a public deployment, email the Climate Prediction Group at IMD Pune and keep the reply. Until then, treat CHIRPS as primary and cite IMD only as a cross-check in the presentation.

There is no API — this is a manual download. Any derived normals we compute should be committed to `data/reference/` with the computation script in `scripts/`, so the derivation is reproducible.

### 2.5 Agmarknet daily mandi prices ✅

Market prices behind every economics figure.

| Field | Value |
|---|---|
| Provider | Directorate of Marketing & Inspection, Ministry of Agriculture & Farmers Welfare |
| Portal | agmarknet.gov.in |
| Access | data.gov.in OGD API, resource *"Current daily price of various commodities from various markets (Mandi)"* |
| Auth | Free API key after registration on data.gov.in |
| Formats | JSON, CSV, XML |
| Fields | Commodity, variety, state, district, market, min / max / modal price, arrival date |
| Unit | ₹ per quintal |
| Licence | **GODL-India** |
| Refresh | Daily |

**Attribution required** under GODL-India: the attribution statement must name the provider, source and licence, and include the URL.

**Practical warnings.**

- The endpoint returns *current* daily prices, not history. Building a 90-day series means running the daily job from now — start it immediately, not the week of submission.
- Coverage is uneven. Many mandis report irregularly; some commodities are missing for long stretches. Your price service must handle empty results, which is why the API contract allows `null` economics.
- Commodity names in the feed do not match our `crop_code` values. A mapping table belongs in `data/reference/crop_commodity_map.csv`, maintained by hand.
- Rate limits are not clearly documented. Cache aggressively and do not call it per user request.

### 2.6 DES Cost of Cultivation ⚠️

Input costs per crop per state — seed, fertiliser, labour, machinery — used for the margin calculation.

| Field | Value |
|---|---|
| Provider | Directorate of Economics & Statistics, Ministry of Agriculture & Farmers Welfare |
| Scheme | Comprehensive Scheme for Studying the Cost of Cultivation of Principal Crops (since 1971) |
| Coverage | 19 major states, principal crops |
| Access | Published reports at desagri.gov.in |
| Format | PDF and tables — **not an API** |
| Licence | ⚠️ Confirm per publication |
| Refresh | Annual, with multi-year lag |

This is the authoritative Indian source for input costs, and the same data CACP uses when recommending MSP — a strong provenance claim in front of judges.

**The catch is the lag.** Published estimates typically run several years behind the current season. Costs must be inflation-adjusted, and the adjustment method must be documented in `data/reference/README.md`. Do not present a 2021 cost figure as if it were current.

Extracted tables go in `data/reference/cost_of_cultivation.csv` with a source citation column naming the report and year for each row.

### 2.7 Soil Health Card ⚠️

District-level nutrient status and fertiliser recommendations.

| Field | Value |
|---|---|
| Provider | Department of Agriculture & Farmers Welfare |
| Portal | soilhealth.dac.gov.in / soilhealth2.dac.gov.in |
| Access | ⚠️ **Web portal only — no documented public API found** |
| Granularity | Village / farmer level via the portal; aggregate dashboards published |
| Licence | Reports are in the public domain per scheme documentation ⚠️ |

**Realistic assessment.** The portal is designed for a farmer to print their own card, not for bulk programmatic access. Our earlier assumption of a `SOIL_HEALTH_API_KEY` may not correspond to anything real.

Options, in order of preference:

1. Use published district-level aggregate nutrient status where available, committed as static reference data.
2. Cite SHC as a *validation* source for SoilGrids rather than a live input.
3. Allow the farmer to enter their own SHC values manually — this is arguably the best product decision anyway, since it uses a real lab test of their actual field.

**Decide this before writing the geo service.** If option 3 is chosen, the API contract needs an optional `soil_override` object on the recommendation request, which is a contract change.

### 2.8 ICAR package of practices ⚠️

Agronomic thresholds — optimal pH range, water requirement, temperature range, duration, sowing windows — that drive the rules-based ranker.

| Field | Value |
|---|---|
| Provider | Indian Council of Agricultural Research, State Agricultural Universities, KVKs |
| Access | Published crop production guides, per crop and per state |
| Format | PDF, printed handbooks |
| Licence | ⚠️ Varies by publication |
| Refresh | Periodic revisions |

These are the numbers our scoring weights depend on, so provenance matters more here than anywhere else. Every threshold in `data/reference/crop_thresholds.csv` carries a `source` column citing the specific publication and page. A judge asking *"why is wheat's optimal pH 6.0–7.5?"* should get a citation, not an opinion.

Prefer state-specific guides over generic national ones where the demo districts are known.

### 2.9 Administrative boundaries ⚠️

District polygons for the admin-area location mode and for `location_resolved`.

Candidate sources — pick one and record the choice here:

| Option | Licence | Note |
|---|---|---|
| GADM | Free for academic use, **not** for commercial redistribution | Common in student projects; check terms |
| Natural Earth | Public domain | Coarse; may lack district detail |
| data.gov.in boundary datasets | GODL-India | Preferred if a suitable one exists |
| Survey of India | Restricted | Authoritative but licensing is involved |

⚠️ Unresolved. District boundaries in India carry political sensitivity around disputed borders; use an Indian government source if at all possible.

---

## 3. What we deliberately do not use

Stating this pre-empts the obvious follow-up questions.

| Not used | Why |
|---|---|
| Scraping agmarknet.gov.in HTML | The OGD API is the sanctioned route; scraping is fragile and of doubtful standing |
| Kaggle "crop recommendation" datasets | Provenance unknown, widely reported as synthetic, would undermine the whole submission |
| Commercial weather APIs | Licence forbids redistribution of forecast data in most free tiers |
| Farmer personal data | No auth in v1; we collect nothing identifying |

The Kaggle row is worth internalising. The popular crop-recommendation dataset circulating on Kaggle has no documented origin, and a judge who recognises it will discount everything built on top of it. Our rules-based approach exists partly to avoid needing it.

---

## 4. Attribution

To be rendered in the app footer and on the "About the data" screen:

> **Data sources.** Soil data © ISRIC — World Soil Information, SoilGrids250m v2.0, licensed under CC BY 4.0. Rainfall data from the Climate Hazards Center (CHIRPS), public domain. Satellite imagery from the Copernicus Sentinel-2 mission, © European Union, contains modified Copernicus Sentinel data. Market prices sourced from Agmarknet via the Open Government Data Platform India (data.gov.in), licensed under the Government Open Data License – India. Agronomic thresholds derived from ICAR published crop production guides; see repository documentation for per-value citations.

This block must ship with the app, not just live in the repo. GODL-India and CC BY 4.0 both make attribution a condition of use.

---

## 5. Reference data in the repository

Static extracts committed to `data/reference/`. Each file carries a `source` column and a companion note in `data/reference/README.md` recording where it came from, when it was extracted, and by whom.

| File | Contents | Source | Owner |
|---|---|---|---|
| `crop_master.csv` | `crop_code`, names, category, seasons | Compiled | — |
| `crop_thresholds.csv` | pH, rainfall, temperature ranges per crop | ICAR guides | — |
| `crop_calendar.csv` | Sowing and harvest windows by crop and state | ICAR / state guides | — |
| `cost_of_cultivation.csv` | Input cost per hectare by crop and state | DES | — |
| `crop_commodity_map.csv` | `crop_code` → Agmarknet commodity name | Manual | — |
| `districts.csv` | State and district codes, centroids | ⚠️ TBD, see 2.9 | — |
| `rainfall_normals.csv` | Long-period rainfall averages by district | CHIRPS-derived | — |

Fill the Owner column with a team member's name. Unowned reference data is how wrong numbers survive to demo day.

---

## 6. Open items

Ordered by how badly each will hurt if left unresolved.

1. **Soil Health Card access model** (2.7) — blocks the geo service design, and may change the API contract. Decide first.
2. **Start the Agmarknet daily job now** (2.5) — price history cannot be backfilled. Every day of delay is a day of missing series.
3. **District boundary source** (2.9) — blocks the admin-area location mode.
4. **IMD licence confirmation** (2.4) — only matters if IMD becomes primary; CHIRPS avoids the issue.
5. **Cost inflation-adjustment method** (2.6) — must be documented before any margin figure is shown.
6. **Verify the SoilGrids GEE asset ID resolves** (2.1) — community-contributed assets occasionally move.

---

## 7. References

Verified against these pages on 2026-08-16.

- [SoilGrids250m 2.0 — Earth Engine Data Catalog](https://developers.google.com/earth-engine/datasets/catalog/ISRIC_SoilGrids250m_v2_0)
- [SoilGrids on Google Earth Engine — ISRIC documentation](https://docs.isric.org/globaldata/soilgrids/access_on_gee.html)
- [Harmonized Sentinel-2 MSI Level-2A — Earth Engine Data Catalog](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED)
- [Copernicus Sentinel Data Legal Notice](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice)
- [CHIRPS Daily v2.0 — Earth Engine Data Catalog](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY)
- [CHIRPS — Climate Hazards Center, UCSB](https://www.chc.ucsb.edu/data/chirps)
- [Current daily price of various commodities from various markets (Mandi) — data.gov.in](https://www.data.gov.in/catalog/current-daily-price-various-commodities-various-markets-mandi)
- [Government Open Data License – India](https://www.data.gov.in/Godl)
- [Comprehensive Scheme for Studying Cost of Cultivation — DES](https://desagri.gov.in/programs-schemes/comprehensive-scheme-for-studying-cost-of-cultivation-of-principal-crops-in-india/)
- [Cost of Cultivation / Production Estimates — DES](https://desagri.gov.in/document-report-category/cost-of-cultivation-production-estimates/)
- [IMD Pune gridded rainfall downloads](https://www.imdpune.gov.in/cmpg/Griddata/Rainfall_25_NetCDF.html)
- [Soil Health Card portal](https://www.soilhealth2.dac.gov.in/)
- [Agmarknet portal](https://agmarknet.gov.in/)

---

## 8. Changelog

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-16 | Initial version. Sources 1, 2, 3, 5 and the Earth Engine platform terms verified against provider documentation; 4, 6, 7, 8, 9 flagged for confirmation. |
