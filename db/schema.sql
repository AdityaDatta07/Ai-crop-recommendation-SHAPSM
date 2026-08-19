-- Crop Recommendation — schema
-- Apply in the Supabase SQL editor. Migrations are manual and reviewed in v1
-- (architecture.md §7); this file is the source of truth for what is deployed.
--
-- Two tables only. Reference data lives in the repo, not here, because it is
-- small, versioned with the code, and must work with no network.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Recommendation results — the 30-day replay window
-- ---------------------------------------------------------------------------
-- The whole response is stored as JSONB rather than shredded into columns. It
-- is written once, read whole, and never queried by its internals; normalising
-- it would buy nothing and would couple the database to a frozen API shape.

create table if not exists public.recommendation_results (
    request_id      text primary key,
    payload         jsonb       not null,
    district_code   text,

    -- Denormalised out of `payload` for the district crowding panel. Both are
    -- derivable from the JSON, but counting a crop across thousands of jsonb
    -- blobs to draw one panel is a query that behaves very differently at 50
    -- rows and at 50,000.
    season          text,
    top_crop_code   text,

    -- True when scripts/seed_advisories.py generated this rather than a person
    -- asking for it. Real output of the real recommender, but a total that
    -- silently mixed the two would overstate how much this tool is consulted.
    seeded          boolean     not null default false,

    created_at      timestamptz not null default now(),
    expires_at      timestamptz not null default now() + interval '30 days',

    -- request_id is the capability token for the replay link, so it must be
    -- long and unguessable. ULIDs are 26 chars; this rejects anything shorter
    -- that might sneak in from a hand-rolled client or a test fixture.
    constraint request_id_is_unguessable check (length(request_id) >= 26)
);

comment on table public.recommendation_results is
    'Computed recommendations, retained 30 days for shareable links and offline replay.';
comment on column public.recommendation_results.request_id is
    'Unguessable ULID. Doubles as the read capability - see policies.sql.';

create index if not exists recommendation_results_expires_at_idx
    on public.recommendation_results (expires_at);

-- Serves the crowding panel: every read is district + season + unexpired.
create index if not exists recommendation_results_district_season_idx
    on public.recommendation_results (district_code, season);

comment on column public.recommendation_results.top_crop_code is
    'Crop ranked first in this advisory. Counts of this column describe ADVISORIES THIS TOOL ISSUED, never farmers or sown area - see apps/api/services/crowding.py.';

create index if not exists recommendation_results_district_idx
    on public.recommendation_results (district_code, created_at desc);

-- ---------------------------------------------------------------------------
-- Market price cache
-- ---------------------------------------------------------------------------
-- Agmarknet is slow and periodically unavailable. A daily job fills this; the
-- API reads it. If both the live call and this cache miss, prices come back
-- null with a warning rather than failing the request.

create table if not exists public.market_prices (
    id              bigint generated always as identity primary key,
    crop_code       text        not null,
    district_code   text,
    mandi           text,
    price_date      date        not null,
    modal_price     integer     not null check (modal_price >= 0),
    min_price       integer     check (min_price >= 0),
    max_price       integer     check (max_price >= 0),
    source          text        not null default 'Agmarknet',
    fetched_at      timestamptz not null default now(),

    constraint price_band_is_ordered check (
        min_price is null or max_price is null or min_price <= max_price
    ),
    -- One observation per crop/mandi/day. Re-running the fetch job upserts
    -- rather than duplicating.
    constraint market_prices_unique_observation
        unique (crop_code, district_code, mandi, price_date)
);

comment on table public.market_prices is
    'Cached mandi prices. Written by the daily fetch job, read by price_service.';

create index if not exists market_prices_lookup_idx
    on public.market_prices (crop_code, district_code, price_date desc);

-- ---------------------------------------------------------------------------
-- Retention
-- ---------------------------------------------------------------------------
-- Called by a scheduled job. Written as a function so the retention rule lives
-- next to the schema it applies to rather than in a cron script somewhere.

create or replace function public.purge_expired_results()
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    removed integer;
begin
    delete from public.recommendation_results where expires_at < now();
    get diagnostics removed = row_count;
    return removed;
end;
$$;

comment on function public.purge_expired_results is
    'Deletes results past their 30-day window. Schedule daily via pg_cron.';
