# apps/api — FastAPI

The HTTP layer plus orchestration. Thin by design: `services/geo` and
`services/ml` are imported Python packages, not separate servers, so this is one
deployable with one log stream.

## Running it

**Python 3.13** — see `.python-version`. Verified working on 3.13 and 3.14;
every dependency resolves to a prebuilt wheel on both, on Windows and Linux.

From the **repository root**, not from this directory — the app imports
`services.geo` and `services.ml` as top-level packages:

```bash
# Windows
py -3.13 -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3.13 -m venv .venv && source .venv/bin/activate

pip install --only-binary=:all: -r apps/api/requirements.txt
cp .env.example .env                                  # defaults work as-is
uvicorn apps.api.main:app --reload --port 8000
```

### Why `--only-binary=:all:`

It forbids pip from compiling anything from source. `pydantic-core` and
`PyYAML` ship per-Python compiled wheels; if your interpreter is newer than a
wheel exists for, pip silently falls back to building them, which needs Rust and
MSVC Build Tools and fails on a clean Windows machine with a wall of Cargo
errors that say nothing about the real cause.

With the flag you instead get an instant, readable failure naming the package
that has no wheel. That is a two-second diagnosis instead of a lost evening.
Keep it in every install command, including CI.

Interactive docs at http://localhost:8000/docs, health at `/health`.

No credentials are needed. `USE_MOCK_GEO=true` is the default, so Earth Engine
is bypassed, and without Supabase configured results are stored in memory.

### Pointing the frontend at it

```bash
# apps/web/.env.local
NEXT_PUBLIC_USE_MOCK_API=false
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## Tests

```bash
pytest                    # from the repo root; 76 tests, no network, no database
```

The ones that matter most are in `tests/test_contract.py`. They validate the
frozen fixtures in `data/seed/api-fixtures/` **and** live API responses against
the same Pydantic models, so `apps/web` and `apps/api` cannot drift apart
without CI failing.

## Layout

```
apps/api/
├── main.py                       app factory, CORS, X-Request-Id middleware
├── core/
│   ├── config.py                 env vars via pydantic-settings
│   ├── errors.py                 the error envelope, in one place
│   ├── reference.py              loads data/reference, enforces provenance
│   └── repository.py             Supabase when configured, memory when not
├── schemas/contract.py           Pydantic mirror of docs/api-contract.md
├── services/
│   ├── recommendation_service.py the orchestrator
│   ├── economics.py              the only place money is calculated
│   ├── calendar_service.py       month-day windows resolved to real dates
│   └── price_service.py          live price -> MSP -> null
└── tests/
```

## Rules this code follows

**The contract document wins.** `schemas/contract.py` mirrors
`docs/api-contract.md`. Where they disagree, the document is right and the code
is the bug.

**Route code never builds an error response by hand.** It raises a typed
exception from `core/errors.py` and one handler produces the envelope. One
place to change, one shape to test.

**Degrade, never collapse.** Earth Engine failing returns null conditions and a
warning, not a 500. A price lookup failing returns null economics and a warning.
Persistence failing logs and still returns the answer. The farmer gets what we
could work out.

**Nulls are never zeros.** A crop with no notified price returns
`"net_margin": null`, and the frontend renders an em dash. Returning `0` would
be a claim we cannot support.

**Startup fails loudly on bad provenance.** `core/reference.py` raises if any
economic value lacks a resolvable source in `sources.yaml`. Refusing to boot
beats serving numbers nobody can trace.

## Not built yet

- **Earth Engine.** `services/geo/earthengine.py` documents exactly what the
  implementation must do; the seam is already wired.
- **Agmarknet prices.** `price_service._live_price` returns `None`, so
  everything falls back to MSP. `/api/v1/prices/{crop_code}` returns an empty
  series rather than inventing one.
- **Rate limiting.** Contract lists `429 RATE_LIMITED` and the error path
  exists, but nothing emits it yet.
- **The `rotation` scoring factor.** Needs field history, which needs auth.
