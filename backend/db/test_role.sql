-- Lets the backend test suite run against the `public` tables as the restricted
-- `connectsphere_test` role (TEST_DATABASE_URL).
--
-- Tests insert their own rows and roll every one of them back, so this role only
-- ever needs to read and write rows: it cannot create, alter or drop tables.
--
-- Run in the Supabase SQL editor. Safe to re-run. Re-run it after adding a table
-- to app/models.py so the role gets access (and an RLS policy) for it too.

begin;

do $$
begin
  if not exists (select from pg_roles where rolname = 'connectsphere_test') then
    create role connectsphere_test login;
  end if;
end $$;

alter role connectsphere_test set search_path = public;

grant usage on schema public to connectsphere_test;
grant select, insert, update, delete
  on public.users, public.venues, public.resources, public.events, public.registrations,
     public.event_clarifications, public.notifications
  to connectsphere_test;
grant usage, select on all sequences in schema public to connectsphere_test;

-- Row Level Security is on for every public table with no policies, which blocks
-- the Supabase API. Let this role (and only this role) through.
do $$
declare
  t text;
begin
  foreach t in array array['users', 'venues', 'resources', 'events', 'registrations',
                       'event_clarifications', 'notifications'] loop
    execute format('drop policy if exists connectsphere_test_all on public.%I', t);
    execute format(
      'create policy connectsphere_test_all on public.%I for all to connectsphere_test '
      'using (true) with check (true)', t);
  end loop;
end $$;

-- The old separate test schema is no longer used.
drop schema if exists test cascade;

commit;

-- Once only, if the role is new, set its password separately (never commit it):
--   alter role connectsphere_test password '<a strong password>';
