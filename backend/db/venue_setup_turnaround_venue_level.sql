-- SCRUM-84 reopened: setup and turnaround time belong to the venue (SCRUM-63 AC9, run
-- venue_setup_turnaround_minutes.sql first), and changing them flags overlapping bookings
-- (AC5). Must match VenueBooking and VenueBookingFlag in app/models.py;
-- `test_database_tables_match_the_models` checks the columns.
--
-- venue_bookings: drops setup_minutes, turnaround_minutes, occupied_start and occupied_end.
--   A booking's occupied period is now worked out from its venue whenever it is read, so
--   the old per-booking values (which nothing writes any more) go. The "no two confirmed
--   bookings overlap" rule compares the event times again: the database cannot see the
--   venue's setup and turnaround, and AC5 lets a venue change leave occupied periods
--   overlapping (they are flagged, not refused). The application checks occupied periods
--   when a booking is requested or approved.
-- venue_booking_flags: one row per booking flagged "Setup or turnaround conflict", with the
--   bookings it overlaps and who raised it. The booking row itself is never touched.
--
-- Run once in the Supabase SQL editor as the project owner. New table, so run
-- db/test_role.sql again too. Safe to re-run.

begin;

alter table public.venue_bookings drop constraint if exists venue_bookings_no_overlapping_confirmed;
alter table public.venue_bookings drop constraint if exists venue_bookings_setup_minutes_range;
alter table public.venue_bookings drop constraint if exists venue_bookings_turnaround_minutes_range;
alter table public.venue_bookings
  drop column if exists occupied_start,
  drop column if exists occupied_end,
  drop column if exists setup_minutes,
  drop column if exists turnaround_minutes;

alter table public.venue_bookings add constraint venue_bookings_no_overlapping_confirmed
  exclude using gist (
    int4range(venue_id, venue_id, '[]') with &&,
    tsrange(start_time, end_time) with &&
  ) where (status = 'confirmed');

create table if not exists public.venue_booking_flags (
  id             serial primary key,
  booking_id     integer   not null unique
                 references public.venue_bookings (id) on delete cascade,
  venue_id       integer   not null references public.venues (id),
  overlaps       jsonb     not null,
  flagged_by_id  integer   references public.users (id),
  flagged_at     timestamp not null default (now() at time zone 'utc')
);

-- Row Level Security on with no policies blocks the Supabase API, like every other table.
alter table public.venue_booking_flags enable row level security;

commit;
