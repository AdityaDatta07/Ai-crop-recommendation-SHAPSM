# data/reference

Static reference data, versioned with the code. Loaded once at API startup
(`apps/api/core/reference.py`), never written to at runtime.

Files here ship in the repo rather than the database because they are small,
reviewable in a pull request, and work with no network — which matters on demo
day. See `docs/architecture.md` §6.

| File | Contents | Provenance |
|---|---|---|
| `sources.yaml` | The provenance register. Every `*_source` key elsewhere resolves here. | — |
| `economics.yaml` | MSP price and A2+FL cost per quintal, average yield per hectare | **cited** |
| `crops.yaml` | pH bands, temperature ranges, water need, calendars, risks | **provisional** |

## The two tiers, and why the split matters

`sources.yaml` marks every source `cited` or `provisional`.

**Cited** means traceable to a named government publication. Prices and costs
come from the two CACP/PIB MSP announcements for 2026-27; yields come from the
Economic Survey 2025-26 statistical appendix. These figures are defensible to a
judge, and the exact citation string travels through the API to the farmer's
screen.

**Provisional** means plausible but unverified. Every agronomic threshold in
`crops.yaml` is in this tier: the pH bands, temperature ranges and sowing
windows are drawn from general crop science, not from an ICAR package of
practices. They are not fabricated, but they are not sourced either.

This matters because those thresholds are what the ranker actually scores on.

The system discloses it through the `warnings` array: while this source is
tiered `provisional`, every recommendation response carries a
`PROVISIONAL_AGRONOMY` warning, which the UI renders above the results.

It deliberately does **not** lower `confidence` to signal this. The API contract
defines `confidence` as derived from `data_completeness` — how much field data
we actually had — so overloading it to also mean "our reference tables are
unverified" would misreport the thing it is specified to report. Two different
uncertainties, two different channels.

Neither makes the numbers right. `apps/api/tests/test_reference.py` asserts this
source stays flagged provisional, so removing the warning requires deliberately
updating that test — it cannot happen by accident.

**Replacing `agronomic_provisional_v1` with a real ICAR reference is the single
highest-value task left on this project.** It converts the ranking from
plausible to defensible, and it is the first thing a domain expert on the panel
will probe.

## Known gaps

- Yields are All-India averages. A district can differ from these by a wide
  margin, and this is the largest single source of error in the economics.
- Barley, lentil and soybean yields are group proxies — the Economic Survey does
  not report them separately. Each is flagged in `yield_note`.
- Sugarcane, potato and onion have no MSP, so they carry null prices and return
  null economics until live Agmarknet data is wired in. That is intended
  behaviour, not a bug: see `docs/architecture.md` principle 2.
- MSP is a floor price with non-universal procurement, not a market price. Live
  mandi prices override it when available.
- Maize yield does not vary by season, though rabi maize out-yields kharif maize
  substantially (5306 vs 2932 kg/ha).

## Changing a number

1. Add or update the entry in `sources.yaml` first. No number lands without one.
2. Update the value, and its `*_note` if there is a caveat worth carrying.
3. Run `pytest apps/api/tests/test_reference.py` — it fails if a `*_source` key
   does not resolve, so provenance cannot silently rot.
