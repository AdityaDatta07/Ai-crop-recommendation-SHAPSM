# Handover — Evaluator's Guide

**For judges, evaluators, and reviewers.**
**Version:** 1.0 · **Last updated:** 2026-08-17

⚠️ **Team: fields marked `[FILL]` must be completed before submission.** An unfilled placeholder is worse than an omission.

---

## 1. Sixty-second orientation

**What this is.** A crop recommendation system for Indian smallholder farmers. A farmer indicates where their land is; the system returns a ranked list of crops with suitability scores, sowing windows, and profit estimates — each with a stated reason and a traceable data source.

**What makes it different from a generic crop-advisory app.** Three things:

1. Recommendations are computed **deterministically**, not by a language model. The same input always produces the same output, and every score decomposes into named agronomic factors.
2. Every figure traces to a **documented, licensed source**. No number appears in the UI without an entry in [`data-sources.md`](./data-sources.md).
3. Where data is unavailable, the system shows **"—", never zero**, and lowers its stated confidence. It refuses to answer rather than guess when data is too sparse.

**The single design decision worth examining.** The language model never decides what to grow. It explains a decision already computed and answers questions strictly from that computed data. Any number it produces that is not present in its input causes the response to be rejected. Rationale in [`ai-design.md`](./ai-design.md) §1.

---

## 2. Current status — honest

`[FILL]` this table from reality on the day of submission. Do not aspirationally mark things complete.

| Component | Status | Notes |
|---|---|---|
| Web app (`apps/web`) | `[FILL: Working / Partial / Not started]` | |
| API (`apps/api`) | `[FILL]` | |
| Geospatial service (`services/geo`) | `[FILL]` | |
| Rules ranker (`services/ml`) | `[FILL]` | |
| LLM explanation | `[FILL]` | |
| Farmer Q&A chat | `[FILL]` | |
| Market price integration | `[FILL]` | |
| Offline mode | `[FILL]` | |
| Deployment | `[FILL]` | |

**Live URL:** `[FILL or: not deployed]`
**Demo video:** `[FILL or: see repository]`

### Known to be incomplete

`[FILL — list honestly. Examples of the right level of specificity:]`

- Scoring weights are expert-set from ICAR guidance but not empirically validated against yield outcomes.
- Domain interviews: `[FILL: number conducted]`. See [`interviews.md`](./interviews.md).
- Soil Health Card integration unresolved — no public API exists. Three options documented in `data-sources.md` §2.7.
- District boundary data source not finalised.

We would rather state these than have you find them.

---

## 3. Verify our claims yourself

We would prefer you checked rather than trusted us. Each row is a claim and how to test it.

| Our claim | How to verify | Where |
|---|---|---|
| Recommendations are deterministic | Submit the same request twice; responses are byte-identical | `POST /api/v1/recommendations` |
| The LLM cannot invent numbers | Inspect the numeric validator and its tests | `services/ml/validation/` |
| Every threshold has a source | Open the reference table; each row has a `source` column | `data/reference/crop_thresholds.csv` |
| Missing data shows as "—", not 0 | Set `USE_MOCK_GEO=true`, request a location with sparse data | `.env` |
| The system refuses unsafe questions | Ask the chat for a pesticide dosage | Chat interface |
| Data licences are as stated | Follow the links in the references section | [`data-sources.md`](./data-sources.md) §7 |
| The API matches its documentation | Run the contract tests | `apps/api/tests/test_contract.py` |

`[FILL: remove any row whose component is not built. A verification instruction that fails is worse than no instruction.]`

---

## 4. Run it in five minutes

```bash
git clone https://github.com/AdityaDatta07/Ai-crop-recommendation-SHAPSM.git
cd Ai-crop-recommendation-SHAPSM
cp .env.example .env
```

**No credentials needed.** Set `USE_MOCK_GEO=true` in `.env` and the system serves fixture data instead of calling Earth Engine. Everything except live satellite queries works offline.

```bash
`[FILL: exact commands]`
# Backend
# Frontend
```

Then open `[FILL: URL]`.

**Demo path:** `[FILL: e.g. drop a pin near Lucknow → select Rabi → 1.5 ha → Get Recommendations]`

If you would rather not run anything, `[FILL: demo video link]` shows the same path in 90 seconds.

---

## 5. Repository tour

Where to look, depending on what you want to assess.

| To assess | Read | Why |
|---|---|---|
| **Whether the design is sound** | [`architecture.md`](./architecture.md) §9 | Decisions and rejected alternatives, in a table |
| **Whether the AI is responsible** | [`ai-design.md`](./ai-design.md) §1, §4 | What the model is and isn't allowed to do |
| **Whether the data is legitimate** | [`data-sources.md`](./data-sources.md) §1 | Every source with licence and verification status |
| **Whether the team is honest** | [`data-sources.md`](./data-sources.md) §6, [`ai-design.md`](./ai-design.md) §9 | Open items and limitations, stated by us |
| **Whether frontend and backend agree** | [`api-contract.md`](./api-contract.md) | Frozen JSON shapes, versioned |
| **Whether users were consulted** | [`interviews.md`](./interviews.md) §6, §7.3 | Interview log and assumptions we abandoned |

### Code layout

```
apps/web/        Next.js PWA — no agronomic logic by design
apps/api/        FastAPI — routing, validation, orchestration
services/geo/    Earth Engine access, imported as a module
services/ml/     Ranker and forecaster
data/reference/  Committed reference data, each row sourced
db/              Schema and Supabase RLS policies
docs/            This documentation
```

**The most important boundary in the codebase:** `apps/web` performs no agronomic calculation and no unit conversion. It displays what the API returns. This means there is exactly one place a wrong number can originate. See [`architecture.md`](./architecture.md) §4.1.

---

## 6. Where the problem statement is addressed

`[FILL: map each requirement of your SIH problem statement to where it is satisfied. Judges score against the statement, not against your architecture — make this easy for them.]`

| Requirement | Addressed by | Status |
|---|---|---|
| `[FILL]` | | |

Do not skip this table. It is the one section that directly answers the question a judge is scoring against, and most teams make the judge do the mapping themselves.

---

## 7. Limitations

Stated in full in [`data-sources.md`](./data-sources.md) §6 and [`ai-design.md`](./ai-design.md) §9. The material ones:

- Soil data is a **250-metre model prediction**, not a soil test of the farmer's field. We surface this as confidence, not as certainty.
- Yield estimates are **historical averages**, not predictions for a specific plot.
- Price forecasts do not model policy shocks, MSP changes, or weather events.
- Scoring weights are **expert-set, not empirically validated.**
- Coverage is limited to districts present in `data/reference/`.
- Risk indicators are crop-typical, not current surveillance data.
- LLM guardrails are layered but not perfect. The design bounds the damage rather than eliminating the risk.

We regard stating these as part of the work. A system that advises on a farmer's income should be explicit about what it does not know.

---

## 8. Team and ownership

`[FILL]`

| Name | Component | Can answer questions on |
|---|---|---|
| | Frontend | |
| | Backend | |
| | Geospatial | |
| | AI / ML | |
| | Data / reference | |
| | | |

**Contact for follow-up:** `[FILL]`

---

## 9. What we would do next

In priority order, with reasoning — not a wish list.

1. **Validate scoring weights against historical district yield data.** The largest gap between what we claim and what we have proven.
2. **Complete domain interviews** with KVK scientists to review the agronomic model. Cheap, fast, and directly addresses (1).
3. **Resolve Soil Health Card access** — most likely by letting farmers enter their own values, which is a real measurement of their actual field rather than a model estimate.
4. **Extract the geospatial service** to isolate Earth Engine cold starts from request latency.
5. **Voice input and output** in regional languages. High value for low-literacy users; a substantial project in its own right.
6. **Crop rotation history** per field, which requires authentication and saved fields.

Items 1 and 2 are the ones we would do first if given another two weeks, because they convert our weakest claim into a defensible one.

---

## 10. Changelog

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-17 | Initial evaluator's guide. |
