-- Adds what SCRUM-84 (Setup and turnaround time in availability and conflict checks)
-- needs to venue_bookings. Must match VenueBooking in app/models.py;
-- `test_database_tables_match_the_models` checks the columns.
--
-- setup_minutes, turnaround_minutes: whole minutes (0-1440) the venue is needed before
--                                    and after the event. Existing bookings get 0.
-- occupied_start / occupied_end:     start_time - setup, end_time + turnaround. Worked out
--                                    by the database (stored, generated).
-- The "no two confirmed bookings overlap" rule now compares occupied periods, so setup
-- and turnaround can't be double-booked whichever code saves the booking. Existing
-- bookings have no setup or turnaround, so they still satisfy it.
--
-- Run once in the Supabase SQL editor as the project owner. No new tables, so
-- db/test_role.sql need not be re-run. Safe to re-run.

begin;

alter table public.venue_bookings
  add column if not exists setup_minutes      integer not null default 0,
  add column if not exists turnaround_minutes integer not null default 0;

alter table public.venue_bookings drop constraint if exists venue_bookings_setup_minutes_range;
alter table public.venue_bookings add constraint venue_bookings_setup_minutes_range
  check (setup_minutes between 0 and 1440);
alter table public.venue_bookings drop constraint if exists venue_bookings_turnaround_minutes_range;
alter table public.venue_bookings add constraint venue_bookings_turnaround_minutes_range
  check (turnaround_minutes between 0 and 1440);

alter table public.venue_bookings
  add column if not exists occupied_start timestamp
    generated always as (start_time - make_interval(mins => setup_minutes)) stored,
  add column if not exists occupied_end timestamp
    generated always as (end_time + make_interval(mins => turnaround_minutes)) stored;

alter table public.venue_bookings drop constraint if exists venue_bookings_no_overlapping_confirmed;
alter table public.venue_bookings add constraint venue_bookings_no_overlapping_confirmed
  exclude using gist (
    int4range(venue_id, venue_id, '[]') with &&,
    tsrange(occupied_start, occupied_end) with &&
  ) where (status = 'confirmed');

commit;
