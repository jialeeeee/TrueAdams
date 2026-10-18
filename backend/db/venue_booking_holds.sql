-- Adds what SCRUM-87 (Venue Staff Place a Tentative Hold) needs to venue_bookings.
-- Must match VenueBooking in app/models.py; `test_database_tables_match_the_models`
-- checks this.
--
-- held_at:          when the hold was placed (naive UTC); the hold starts then.
-- held_by_id:       the Venue Staff member who placed it.
-- hold_expires_at:  when it expires (Singapore time, no time zone), set by Venue Staff.
-- A hold is a booking with status 'tentative' (status is plain text, so it needs no
-- change here). All three start empty, so existing bookings are unchanged.
--
-- Run once in the Supabase SQL editor as the project owner. No new tables, so
-- db/test_role.sql need not be re-run. Safe to re-run.

begin;

alter table public.venue_bookings
  add column if not exists held_at          timestamp,  -- UTC, no time zone
  add column if not exists held_by_id       integer references public.users (id),
  add column if not exists hold_expires_at  timestamp;  -- Singapore time, no time zone

commit;
