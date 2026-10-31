-- SCRUM-88 (Venue becomes unavailable after booking): the table of confirmed bookings
-- flagged "Venue unavailable: replacement needed". Must match VenueReplacementFlag in
-- app/models.py; `test_database_tables_match_the_models` checks the columns.
--
-- An unavailable period is a row of the existing venue_blocks table, so it needs no change.
-- venue_replacement_flags: one row per flagged booking, with the unavailable period that
--   first flagged it, who recorded that, when, and a status ("flagged" until a replacement
--   is approved, SCRUM-89). The booking row itself is never touched.
--
-- Run once in the Supabase SQL editor as the project owner. New table, so run
-- db/test_role.sql again too. Safe to re-run.

begin;

create table if not exists public.venue_replacement_flags (
  id             serial primary key,
  booking_id     integer     not null unique
                 references public.venue_bookings (id) on delete cascade,
  venue_id       integer     not null references public.venues (id),
  block_id       integer     not null references public.venue_blocks (id) on delete cascade,
  status         varchar(20) not null default 'flagged',
  flagged_by_id  integer     references public.users (id),
  flagged_at     timestamp   not null default (now() at time zone 'utc')
);

-- Row Level Security on with no policies blocks the Supabase API, like every other table.
alter table public.venue_replacement_flags enable row level security;

commit;
