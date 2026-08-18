# Connecting the real data sources

Both integrations are written and both are **unverified** — no one has run them
against live credentials. Until you do, `USE_MOCK_GEO=true` and the MSP fallback
carry the app, and everything works.

Read the failure behaviour first, because it is what makes this safe to attempt
close to a deadline: **neither source can break the app.** Earth Engine failing
returns null conditions and a warning. Agmarknet failing falls back to MSP. If
you run out of time, ship on mocks and lose nothing but freshness.

---

## 1. Earth Engine — real Sentinel-2 and SoilGrids

Gets you: measured soil pH and organic carbon, real NDVI/SAVI/NDMI/EVI for the
drawn field, a genuine 24-month NDVI history, and the satellite tile overlay on
the map.

### Setup

1. Create a Google Cloud project.
2. Enable the **Earth Engine API** on it.
3. Register the project at https://code.earthengine.google.com/register — pick
   **noncommercial / research**, which is free. Approval is usually minutes but
   can take a day, so **do this first**.
4. Create a service account, give it the **Earth Engine Resource Viewer** role,
   and download the JSON key.
5. Configure:

   ```bash
   GEE_PROJECT_ID=your-project-id
   GEE_PRIVATE_KEY_PATH=./secrets/gee-key.json   # local
   USE_MOCK_GEO=false
   ```

   For deployment, base64 the key instead — Render has no filesystem you want a
   private key sitting on:

   ```bash
   base64 -w0 gee-key.json          # macOS/Linux
   certutil -encode gee-key.json tmp.b64   # Windows
   ```

   ```bash
   GEE_SERVICE_ACCOUNT_KEY_B64=<the base64 string>
   ```

6. `pip install --only-binary=:all: -r apps/api/requirements.txt` (the
   `earthengine-api` package is already listed).
7. Restart and check `/health` — `geo_service` should read `earthengine`.

### What to expect

- **The first request will be slow.** Earth Engine cold starts run 10–15s, and
  the NDVI history makes 24 sequential calls. The frontend has a 30s timeout,
  but warm the service before demoing.
- **`secrets/` is git-ignored.** Keep it that way. A leaked service-account key
  is a real incident, not a slap on the wrist.
- **NPK stays null.** SoilGrids does not carry nitrogen, phosphorus or
  potassium. The Soil Health Card portal does but has no bulk API. Expect
  `data_completeness` around 0.6 on the real path versus 0.92 on mocks — that
  is honest, not a regression.
- **Weather stays null too.** IMD normals are not wired yet; see
  `docs/data-sources.md`.

### Known gap

`get_conditions` samples a circular buffer around the district centroid, not the
polygon the farmer drew. Fine for a district selection, wrong for a drawn field.
The TODO is marked in `services/geo/earthengine.py`.

---

## 2. Agmarknet — live mandi prices

Gets you: what farmers are actually paid, replacing MSP. MSP is a floor with
non-universal procurement; the mandi price is the real number.

### Setup

1. Register at https://www.data.gov.in and generate an API key.
2. `DATA_GOV_IN_API_KEY=your-key` (or `MARKET_PRICE_API_KEY`).
3. Restart. No flag needed — the client activates when a key is present.

### The User-Agent trap

**data.gov.in's WAF silently drops requests with a library User-Agent.** Not a
403 — the connection simply hangs until it times out, which reads like a network
fault and sent us chasing IPv6 and query filters for an evening.

Measured on the same URL, same key, same machine:

| Client | Result |
|---|---|
| `python-httpx/0.27.2` | ReadTimeout after 20.4s |
| `python-httpx/0.27.2`, forced IPv4 | ReadTimeout after 20.2s |
| Browser User-Agent | **HTTP 200 in 0.5s** |
| Browser UA, forced IPv4 | **HTTP 200 in 0.4s** |
| curl | HTTP 200 in 0.4s |

So `BROWSER_HEADERS` in `agmarknet.py` is load-bearing, not decoration. Two
tests assert it stays — one on the constant, one on the actual wire — because
dropping it reverts live prices to the MSP fallback silently.

### Verify it first

The field names in `apps/api/services/agmarknet.py` follow the published docs,
but **data.gov.in has renamed fields between revisions** and this parser has
never met a live response. Before trusting it:

```bash
curl "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070?api-key=YOUR_KEY&format=json&limit=1"
```

Compare the keys in `records[0]` against `_first(...)` in `parse_records`. The
parser accepts several spellings and skips records it cannot read, so a mismatch
shows up as *no prices* rather than wrong prices — check the API logs for
`Agmarknet request failed` or an absence of `Agmarknet: N records`.

### How it behaves

- Tries the district first, then widens to the state. Not every mandi trades
  every crop every day.
- Takes the **median** modal price of the freshest day, not the mean. There is
  always one mis-keyed entry, and a mean would chase it.
- Prices older than 30 days are discarded rather than shown as current.
- `price_source` says which was used, so the screen never hides whether a figure
  is a live mandi price or the MSP floor.

### Crop name mapping

Agmarknet's commodity names are inconsistent — "Bengal Gram(Gram)(Whole)",
"Paddy(Dhan)(Common)", "Arhar (Tur/Red Gram)(Whole)". `COMMODITY_NAMES` maps our
stable crop codes to the aliases, trying each in turn. A test asserts every crop
in `data/reference` has a mapping, so adding a crop without one fails the build.
If a crop returns no prices with a valid key, a wrong alias is the first
suspect — check the exact spelling on the Agmarknet portal.
