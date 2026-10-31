-- Adds what SCRUM-89 (Coordinator replaces an unavailable venue) needs to venue_bookings.
-- Must match VenueBooking in app/models.py; `test_database_tables_match_the_models` checks
-- the columns. Run db/venue_unavailable_periods.sql (SCRUM-88) first.
--
-- replaces_booking_id: the flagged booking a replacement request is for; NULL for every
--                      other request, so existing rows are unchanged.
-- Approving a replacement sets the flagged booking's status, and its flag's status in
-- venue_replacement_flags, to 'replaced'; no schema change is needed for that.
--
-- Run once in the Supabase SQL editor as the project owner. No new tables, so
-- db/test_role.sql need not be re-run. Safe to re-run.

begin;

alter table public.venue_bookings
  add column if not exists replaces_booking_id integer references public.venue_bookings (id);

commit;
