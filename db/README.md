# db

Postgres schema for Supabase. Applied by hand in the SQL editor — migrations are
manual and reviewed in v1 (`docs/architecture.md` §7).

## Applying it

1. Create a Supabase project.
2. SQL editor → run `schema.sql`, then `policies.sql`. Order matters: the
   policies reference tables the schema creates.
3. Put the credentials in `.env` at the repo root:

   ```
   SUPABASE_URL=https://<project>.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=<service role key>   # server only, bypasses RLS
   NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon key>       # browser, subject to RLS
   ```

4. Restart the API. `GET /health` reports `"db": "ok"` once it can reach the
   table, `"memory"` when Supabase is not configured, and `"unreachable"` when
   it is configured but failing.

Without step 3 the API runs against an in-memory store. Everything works except
that results are lost on restart, so shareable links do not survive a redeploy.

## The security model, briefly

No auth in v1, so there is no session to steal. A result is readable by whoever
knows its `request_id` — an unguessable 26-character ULID. That is the whole
capability: it is what makes a shareable link work without an account, and it is
why `request_id` must never become sequential or predictable.

Writes are server-side only. The service-role key never leaves the backend; the
browser only ever holds the anon key.

**The one thing to watch:** the read policy permits `SELECT` broadly and relies
on the absence of a listing endpoint plus an unguessable key. If anyone adds an
endpoint that returns results without filtering by `request_id`, the policy has
to be tightened in the same change. The commented block at the end of
`policies.sql` shows the shape that takes once auth exists.

## Retention

`purge_expired_results()` deletes rows past the 30-day window. Schedule it daily:

```sql
select cron.schedule('purge-results', '0 3 * * *', 'select public.purge_expired_results()');
```

Nothing breaks if it never runs — reads filter on `expires_at` anyway — but the
table grows without it.
