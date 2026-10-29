-- Adds what SCRUM-86 (Tentative Venue Holds Expire, Week 7 customer change 4) needs to
-- venue_bookings. Must match VenueBooking in app/models.py;
-- `test_database_tables_match_the_models` checks this.
--
-- hold_warned_at:  when the coordinator was told the hold expires within 24 hours
--                  (naive UTC), so the warning is sent once. It starts empty, so every
--                  existing hold is still due its warning.
-- An expired hold gets the status 'expired' from the expiry check (status is plain
-- text, so it needs no change here).
--
-- Run once in the Supabase SQL editor as the project owner, after
-- db/venue_booking_holds.sql. No new tables, so db/test_role.sql need not be re-run.
-- Safe to re-run.

begin;

alter table public.venue_bookings
  add column if not exists hold_warned_at timestamp;  -- UTC, no time zone

commit;
