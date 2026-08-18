# apps/web — Next.js PWA

The farmer-facing client. Captures a location and season, calls
`POST /api/v1/recommendations`, and renders the ranked result.

## Running it

```bash
cd apps/web
npm ci                       # wipes any partial node_modules and installs from the lockfile
cp .env.local.example .env.local
npm run dev                  # http://localhost:3000
```

`NEXT_PUBLIC_USE_MOCK_API=true` in `.env.local` serves the fixtures in
`data/seed/api-fixtures/`, so this runs with no backend at all. Flip it to
`false` once `apps/api` is up. Keep the mock path working — it is the demo
fallback if the venue network dies.

## Scripts

| Script | What it does |
|---|---|
| `npm run dev` | Dev server (syncs fixtures first) |
| `npm run build` | Production build (syncs fixtures first) |
| `npm run typecheck` | `tsc --noEmit`, including the fixture contract check |
| `npm run lint` | ESLint via `next lint` |
| `npm run sync:fixtures` | Copies `data/seed/api-fixtures/` into `public/fixtures/` |

## Layout

```
src/
├── app/
│   ├── page.tsx                          location + season form
│   ├── r/[request_id]/page.tsx           ranked results
│   └── r/[request_id]/[crop_code]/       one crop in full
├── components/
│   ├── ui/                               Button, Card, Badge, Input, Select, Label, Skeleton
│   └── recommendation/                   domain components
├── lib/
│   ├── client.ts                         the only place that talks to the API
│   ├── mock.ts                           fixture transport
│   ├── queries.ts                        React Query hooks
│   ├── cache.ts                          offline replay of past results
│   ├── format.ts                         display formatting — null renders as —
│   └── api-error.ts                      error envelope → typed ApiError
├── contract/fixtures.check.ts            compile-time check: fixtures vs contract
└── types/api.ts                          TypeScript mirror of docs/api-contract.md
```

## The one rule

**No agronomic logic, no economics maths, no unit conversion in this app.** It
displays what the API returns. `src/lib/format.ts` formats; it never computes.
If a number looks wrong, the bug is in `apps/api`, and that is the point —
there is exactly one place a wrong number can come from.

Two consequences worth remembering:

- A `null` economics field renders as `—`, never as `0`. A zero margin and an
  unknown margin are different claims.
- Suitability scores are relative within a single response. Never compare them
  across requests, and never display them as a percentage of anything absolute.

## Not built yet

- **Polygon location.** The contract supports a drawn field boundary; the UI
  offers district and point only. Needs MapLibre GL plus a draw surface.
- **Service worker.** `cache.ts` gives offline replay of past results via
  localStorage. True offline install needs a service worker and a move to
  IndexedDB — swap that module's internals and nothing above it changes.
- **i18n.** Crop names already carry `name_hi` from the API. UI strings are
  still hardcoded English and will need extracting to locale files.
