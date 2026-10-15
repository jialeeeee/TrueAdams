-- Adds what SCRUM-40 (Approve a Venue Booking Request) records on venue_bookings.
-- Must match VenueBooking in app/models.py; `test_database_tables_match_the_models`
-- checks this.
--
-- decided_at:     when the request was approved (UTC, no time zone).
-- decided_by_id:  the Venue Staff member who approved it.
-- Both start empty, so existing bookings are unchanged.
--
-- Run once in the Supabase SQL editor as the project owner. No new tables, so
-- db/test_role.sql need not be re-run. Safe to re-run.

begin;

alter table public.venue_bookings
  add column if not exists decided_at     timestamp,  -- UTC, no time zone
  add column if not exists decided_by_id  integer references public.users (id);

commit;
