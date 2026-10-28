-- Lets an event have several pending venue requests, for SCRUM-85 (Several Venues for
-- One Event, Week 7 customer change 3). Must match VenueBooking in app/models.py.
--
-- SCRUM-39 allowed one pending request per event (assumption A6), enforced by the unique
-- index venue_bookings_one_pending_per_event from db/venue_booking_requests.sql. An event
-- that needs several spaces asks for each venue separately, so the index is dropped
-- (assumption A1 in docs/test-cases/SCRUM-85-several-venues-for-one-event.md). The app
-- still refuses a second pending request for the same venue at an overlapping time (A2).
-- No column changes, so `test_database_tables_match_the_models` is unaffected, but the
-- SCRUM-85 tests fail on Supabase until this has been run.
--
-- Run once in the Supabase SQL editor as the project owner. No new tables, so
-- db/test_role.sql need not be re-run. Safe to re-run.

begin;

drop index if exists public.venue_bookings_one_pending_per_event;

commit;
