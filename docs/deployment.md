# Deploying Beej Nirnay

**I could not run any of this for you.** I have no hosting account, no deploy
credentials, and the environment I work in has no outbound network for pushing.
Everything below is verified as far as it can be from inside the repository —
the build config, the environment contract, the health check — and the steps
that need your accounts are marked as yours.

---

## 1. What has to be deployed

Two services, not one. This is the first thing that trips people up.

| Part | What it is | Needs |
|---|---|---|
| `apps/api` | FastAPI, Python 3.10+ | A Python host that can hold a process |
| `apps/web` | Next.js 15 App Router | Any Node host, or Vercel |

The web app calls the API over HTTP. They can live on different hosts; the web
app only needs `NEXT_PUBLIC_API_BASE_URL` pointing at the API.

## 2. Before anything else: the database

The demo runs on SQLite at `data/results.db`. **That will not survive a deploy**
on most hosts — their filesystems are ephemeral, so every restart loses every
shareable `/r/<id>` link and empties the crowding panel.

For a real deployment, apply the schema to Supabase and set the two variables:

```bash
# In the Supabase SQL editor, in this order:
#   1. db/schema.sql
#   2. db/policies.sql
```

Then set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` on the API only. The
service-role key bypasses row-level security entirely and must never reach the
browser — the web app gets `NEXT_PUBLIC_SUPABASE_ANON_KEY` and nothing else.

If you skip this, the app still works, and every restart wipes the results.

## 3. Environment variables

Copy `.env.example`. The ones that actually change behaviour:

| Variable | Where | If unset |
|---|---|---|
| `USE_MOCK_GEO` | API | `true` — serves mock conditions. Set `false` in production. |
| `GEE_PROJECT_ID`, `GEE_SERVICE_ACCOUNT_KEY_B64` | API | Earth Engine is skipped; conditions degrade and the UI says so |
| `DATA_GOV_IN_API_KEY` | API | No live mandi prices; economics fall back to MSP |
| `GEMINI_API_KEY`, `LLM_MODEL` | API | Chat answers from templates only — still useful, never invents |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | API | SQLite, lost on restart |
| `CORS_ALLOWED_ORIGINS` | API | `http://localhost:3000` — **must** be your real web origin or the browser blocks every call |
| `NEXT_PUBLIC_API_BASE_URL` | Web | Points at localhost, so nothing works |

Prefer `GEE_SERVICE_ACCOUNT_KEY_B64` over `GEE_PRIVATE_KEY_PATH` on a host with
no filesystem you would want to leave a private key on.

## 3a. Docker, or not?

**Not for this.** Recommendation: Vercel for the web app, Render for the API.

Docker's value is reproducibility and portability across hosts that do not
understand your stack. Neither applies here:

- Vercel runs Next.js natively and better than any container you would write —
  it handles the build cache, image optimisation and CDN without configuration.
- Render and Railway build Python straight from `requirements.txt`.
- Reproducibility is already handled: every version in `requirements.txt` is
  pinned, and a clean-virtualenv install was verified to boot the whole API.

A Dockerfile would add a file to maintain, a slower build loop, and a new class
of failure (image layers, registry auth) in exchange for nothing you need this
week.

**Use Docker instead if** you are deploying to a college VM, a VPS, or any
single machine you control — then one `docker compose up` beats configuring two
services by hand. In that case the API image must be built from the
REPOSITORY ROOT, not `apps/api`, because the API imports `services/` and reads
`data/`. No Dockerfile is committed here: an untested Dockerfile is worse than
none, and this environment has no Docker to test one in.

## 4. Deploy the API

Any host that runs a Python process. Render, Railway, Fly.io and Google Cloud
Run all work. Two things to get right:

**Render, step by step:**

1. render.com -> New -> Web Service -> connect the GitHub repo.
2. **Root Directory: leave BLANK.** This is the one setting people get wrong.
   The API imports `services.geo` and reads `data/reference/*.yaml`, both at
   the repository root. Setting it to `apps/api` produces
   `ModuleNotFoundError: services` and the log does not explain why.
3. Runtime: Python 3. `runtime.txt` pins 3.11.
4. Build command: `pip install -r requirements.txt`
5. Start command: `uvicorn apps.api.main:app --host 0.0.0.0 --port $PORT`
6. Add the environment variables from §3. At minimum set
   `CORS_ALLOWED_ORIGINS` to your Vercel URL once you have it.
7. Deploy, then open `/health` and check each backend.

- **Earth Engine cold starts are slow.** The first request after a scale-to-zero
  can exceed the client's 15-second timeout, and the app then serves a recorded
  fallback with an amber notice. On a free tier that sleeps, expect that on the
  first request of a demo. Warm it before you present.
- `/health` reports each dependency separately. Check it after deploy: it will
  tell you whether Earth Engine, Agmarknet and the database are actually
  reachable rather than silently degraded.

## 5. Deploy the web app

```bash
cd apps/web
npm ci
npm run build      # runs sync:fixtures first, then next build
npm start
```

**Vercel, step by step:**

1. vercel.com -> Add New -> Project -> import the repo.
2. **Root Directory: `apps/web`.**
3. **Turn ON "Include source files outside of the Root Directory".** The
   `prebuild` step runs `scripts/sync-fixtures.mjs`, which reads
   `../../../data/seed/api-fixtures` at the repository root. Without this the
   build fails on a missing directory.
4. Environment variable: `NEXT_PUBLIC_API_BASE_URL` = your Render URL, with no
   trailing slash.
5. Deploy. Vercel gives you `https://<project>.vercel.app` — that is your URL.
6. Go back to Render and set `CORS_ALLOWED_ORIGINS` to that exact origin, then
   redeploy the API. Until you do, every request from the browser is blocked
   and the site looks broken with no visible error except in the console.

**I could not run `next build` end to end** — the Linux sandbox has no SWC
binary for this platform and no network to fetch one. `tsc --noEmit` and
ESLint both pass, so type and lint errors are ruled out, but run the build
yourself before you rely on it.

## 6. Seed the crowding panel

A fresh database has no advisories, so the Market crowding tab correctly shows
nothing. To populate it:

```bash
USE_MOCK_GEO=true python scripts/seed_advisories.py    # ~470 advisories
python scripts/seed_advisories.py --clear              # remove them again
```

Every seeded row is flagged, and the panel says how many of its total came from
setup rather than from a person.

## 7. After deploying — check these, in order

1. `GET /health` — all backends report something other than `unreachable`.
2. Load the start page. If it is blank, `NEXT_PUBLIC_API_BASE_URL` is wrong.
3. Run one recommendation. If it fails with a CORS error in the console,
   `CORS_ALLOWED_ORIGINS` does not include your web origin.
4. Open the result, then reload it by URL. If it 404s, persistence is not
   working — you are on ephemeral SQLite.
5. Ask the chat "when should I sow?" — that is the template path and must work
   with no LLM key at all. Then ask something open-ended to test the key.
6. Ask it "what pesticide should I spray". It must refuse. If it answers, stop
   and tell me.
7. Print to PDF from the results page and check the background image and the
   decorative shapes are absent.

## 8. What I have not been able to verify

Stated plainly so you can check these first rather than discover them live:

- **The Gemini call has never run.** The sandbox cannot reach
  `generativelanguage.googleapis.com`, so the request shape, the model id and
  your key are all unverified end to end. The chat's template answers and every
  refusal are fully tested and do not depend on it.
- **`next build` has not been run.** See §5.
- **Earth Engine has never run here.** All satellite paths were exercised
  against mocks and fakes.
- **None of the outbound links have been opened** except the two PIB releases
  and the JanSamarth portal. The link test checks scheme and domain, not that
  each page still exists.

## 9. Changelog

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-20 | First deployment guide. |
