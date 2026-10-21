-- Adds what SCRUM-63 (Maintain the Venue Catalogue) needs: the venue change history.
-- Must match VenueChange in app/models.py; `test_database_tables_match_the_models`
-- checks this.
--
-- venue_changes: one row per add or edit of a venue.
--   action:        'added' or 'edited'.
--   changed_by_id: the Venue Staff member who made the change.
--   changed_at:    when (naive UTC).
--   changes:       {"<field>": {"from": ..., "to": ...}} for each field touched.
--
-- Run once in the Supabase SQL editor as the project owner, then re-run
-- db/test_role.sql so the test role can use the new table. Safe to re-run.

begin;

create table if not exists public.venue_changes (
  id             serial primary key,
  venue_id       integer     not null references public.venues (id),
  action         varchar(10) not null,
  changed_by_id  integer     not null references public.users (id),
  changed_at     timestamp   not null default (now() at time zone 'utc'),
  changes        jsonb       not null
);

-- Row Level Security on with no policies blocks the Supabase API, like every other table.
alter table public.venue_changes enable row level security;

commit;
