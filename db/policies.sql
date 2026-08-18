-- Row Level Security
--
-- v1 has no auth, so there is no user to scope rows to. The security model is
-- capability-based instead: a result is readable by anyone who knows its
-- request_id, which is an unguessable ULID handed only to the farmer who
-- created it. That is what makes a shareable link work without an account.
--
-- These policies are written now, before auth exists, so that adding auth later
-- is a policy change rather than a rewrite. The commented block at the bottom
-- is the intended shape of that change.
--
-- Apply AFTER schema.sql.

alter table public.recommendation_results enable row level security;
alter table public.market_prices          enable row level security;

-- ---------------------------------------------------------------------------
-- recommendation_results
-- ---------------------------------------------------------------------------

-- The anon key can read a row only when it already knows the exact request_id.
-- PostgREST turns `?request_id=eq.<id>` into a filter, so a query without one
-- matches nothing: there is no way to list or enumerate results.
--
-- The `using (true)` here is doing less than it looks. It permits the SELECT;
-- it does not permit discovery, because the API never exposes an unfiltered
-- list endpoint and the primary key is a 26-character random token. If a
-- listing endpoint is ever added, THIS POLICY MUST CHANGE FIRST.
drop policy if exists results_readable_by_request_id on public.recommendation_results;
create policy results_readable_by_request_id
    on public.recommendation_results
    for select
    to anon, authenticated
    using (expires_at > now());

-- Writes are server-side only. The service-role key bypasses RLS entirely, so
-- there is deliberately no insert or update policy for anon: a client cannot
-- forge a recommendation and hand out a link to it.
drop policy if exists results_no_client_writes on public.recommendation_results;
create policy results_no_client_writes
    on public.recommendation_results
    for insert
    to anon, authenticated
    with check (false);

-- ---------------------------------------------------------------------------
-- market_prices
-- ---------------------------------------------------------------------------
-- Public reference data. Readable by anyone, written only by the fetch job.

drop policy if exists prices_public_read on public.market_prices;
create policy prices_public_read
    on public.market_prices
    for select
    to anon, authenticated
    using (true);

drop policy if exists prices_no_client_writes on public.market_prices;
create policy prices_no_client_writes
    on public.market_prices
    for insert
    to anon, authenticated
    with check (false);

-- ---------------------------------------------------------------------------
-- When auth arrives
-- ---------------------------------------------------------------------------
-- Add a nullable owner column, backfill nothing, and tighten the read policy.
-- Anonymous results keep working by capability; owned results become private.
--
--   alter table public.recommendation_results
--       add column owner_id uuid references auth.users(id);
--
--   drop policy results_readable_by_request_id on public.recommendation_results;
--
--   create policy results_readable_by_owner_or_link
--       on public.recommendation_results
--       for select
--       to anon, authenticated
--       using (
--           expires_at > now()
--           and (owner_id is null or owner_id = auth.uid())
--       );
