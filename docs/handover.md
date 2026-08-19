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
- **The crowding panel does not know what farmers are planting.** It counts advisories *this tool* issued and reads past mandi prices. See below.
- LLM guardrails are layered but not perfect. The design bounds the damage rather than eliminating the risk.

We regard stating these as part of the work. A system that advises on a farmer's income should be explicit about what it does not know.

---

### 7.1 The one feature we cut down rather than fake

The brief asked for a **district glut-risk dashboard**: warn a farmer when too
many people in their district are about to plant the same crop.

That needs district-level sowing intentions. Nobody publishes them in time to
act on, and we have a handful of users rather than thousands. The obvious move
was a plausible aggregate — *"62% of Nashik plots are going to onion"* — which
would have demoed well and been an invention. Every other number in this project
is traceable to a source, and one fabricated statistic devalues all of them.

So the panel answers two narrower questions that are actually answerable:

1. **Concentration in our own advice.** We store every advisory with its
   district and season, so we can say truthfully: *"ranked first in 10 of the 12
   advisories issued for Lucknow this rabi."* That is a claim about this tool,
   not about farmers — and it carries a real warning, because an advisory
   followed at scale becomes a cause of the glut it is warning about.
2. **What the market already did.** A glut leaves a fingerprint: the crop is
   cheap in the month it is harvested. That is observable from the Agmarknet
   prices we record. It is backward-looking and labelled as such.

Both refuse to produce a figure below a minimum sample —
`MIN_ADVISORIES = 8` is derived, not chosen: one advisory must move the share by
less than half a band width, or the bands are noise.

**Expect the price column to be empty, and know why.** data.gov.in publishes
only a current daily snapshot; there is no historical endpoint. The app records
what it sees, so a harvest-month comparison needs prices observed *during* a
harvest — for a rabi crop, April. A store that is two days old holds two days of
one month and can never make that comparison, however many rows it has. This
will not fill in before a demo, and the panel says so rather than showing an
unexplained blank.

`apps/api/tests/test_crowding.py` fails the build if the words "farmer",
"plot", "hectare", "sown" or "acre" appear in any crowding string, because a
correctly-named Python field with *"62% of farmers"* in its translation would
otherwise pass every other test we have.

**Seeding the demo.** A fresh clone has no advisories, so the panel correctly
shows nothing. To populate it:

```bash
USE_MOCK_GEO=true python scripts/seed_advisories.py     # ~470 advisories
python scripts/seed_advisories.py --clear               # remove them again
```

These are real output of the real recommender across varied plot sizes,
irrigation types and soil cards — not hand-written rows. Every one is flagged
`seeded`, and the panel says how many of its total came from setup rather than
from a person asking. The script refuses to run when the geo provider is
degraded, because condition-free advisories rank identically in every district
and would render as a confident number describing nowhere.

### 7.1a Language coverage — partial, and deliberately visible

Seven languages are wired end to end: English, Hindi, Marathi, Bengali,
Gujarati, Tamil, Telugu. The *machinery* is complete for all seven — locale
switching, browser-language detection, speech recognition and text-to-speech
tags, and crop names for all 16 crops in every language.

The *translations* are not. Current state:

| Language | UI strings | Notes |
|---|---|---|
| English | 662/662 | Source of truth |
| Hindi | 662/662 | Complete; the build fails if it regresses |
| Marathi | 155/662 | Forms, results chrome, navigation |
| Gujarati | 155/662 | Same coverage as Marathi |
| Bengali | 90/662 | Forms and navigation |
| Tamil | 0/662 | Machinery ready, strings pending |
| Telugu | 0/662 | Machinery ready, strings pending |

**A missing string falls back to English, not to its key path.** That was
changed deliberately when the language count went from two to seven: a farmer
reading Telugu who hits an untranslated string sees a real English sentence
and knows to switch, rather than a dotted identifier in Latin script that
looks like a crash.

`scripts/build_locale.py` takes a flat `{"dot.path": "translation"}` JSON and
merges it safely — it rejects any path that does not exist in en.json rather
than silently creating a branch. A native speaker can complete a language
without touching the app.

**None of the non-English translations have been reviewed by a native
speaker.** Agricultural vocabulary is specialist — "usable rainfall",
"A2+FL cost", "support price is not a guarantee" — and a mistranslation there
is exactly the kind of silent error the rest of this project is built to
prevent. Treat them as drafts, on the same footing as the crops.yaml
thresholds.

---

### 7.2 Role-based access and audit log — deferred, with the groundwork done

Not built, and the reason is scheduling rather than difficulty. Doing it
properly means user accounts, session handling, an ownership model for saved
advisories, an append-only audit table and a UI for all of it — roughly a week.
Set against the rest of the backlog that was the wrong trade, and half-built
auth is worse than none: it implies a guarantee it does not keep.

What already exists:

- **Row-level security is on and restrictive.** `db/policies.sql` enables RLS
  on both tables, allows reads only through an unguessable 26-character
  request id that also expires, and denies client writes outright with
  `with check (false)`. Every write goes through the server.
- **The service-role key never reaches the browser.** The client holds only the
  anon key and reads through those policies. That separation is the part that
  would be expensive to retrofit, and it is already correct.
- **The migration is written down.** The end of `policies.sql` carries the
  exact `alter table` and replacement policy for adding `owner_id`, chosen so
  that anonymous results keep working by capability while owned results become
  private. No data migration is required.

What is genuinely missing: authentication itself, roles (farmer / extension
officer / administrator), and the audit log — there is no `audit_events` table
and nothing writes one today. Anyone claiming this system currently has an
audit trail would be wrong.

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
5. **Real crowding data.** The current panel counts our own advice because
   district sowing intentions are not published. A state agriculture department
   feed, or enough users to make the counts meaningful, would turn this from a
   disclosure about the tool into the warning the brief actually asked for.
6. **Crop rotation history** per field, which requires authentication and saved fields.

Items 1 and 2 are the ones we would do first if given another two weeks, because they convert our weakest claim into a defensible one.

---

## 10. Changelog

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-17 | Initial evaluator's guide. |
| 1.1 | 2026-08-19 | Voice input and spoken advisory. District crowding panel, and §7.1 on why it was cut down rather than faked. |
| 1.2 | 2026-08-19 | §7.2 records the RBAC deferral and what groundwork is already in place. |
