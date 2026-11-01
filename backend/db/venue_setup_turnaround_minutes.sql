-- Adds what the reopened SCRUM-63 (Maintain the Venue Catalogue, AC9) needs to venues.
-- Must match Venue in app/models.py; `test_database_tables_match_the_models` checks the
-- columns.
--
-- setup_minutes, turnaround_minutes: whole minutes (0-1440) the venue is needed before and
--                                    after an event. NULL means none set, which every
--                                    scheduling check treats as 0, so existing venues keep
--                                    their behaviour.
--
-- Run once in the Supabase SQL editor as the project owner. No new tables, so
-- db/test_role.sql need not be re-run. Safe to re-run.

begin;

alter table public.venues
  add column if not exists setup_minutes      integer,
  add column if not exists turnaround_minutes integer;

alter table public.venues drop constraint if exists venues_setup_minutes_range;
alter table public.venues add constraint venues_setup_minutes_range
  check (setup_minutes between 0 and 1440);
alter table public.venues drop constraint if exists venues_turnaround_minutes_range;
alter table public.venues add constraint venues_turnaround_minutes_range
  check (turnaround_minutes between 0 and 1440);

commit;
