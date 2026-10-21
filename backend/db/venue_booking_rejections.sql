-- SCRUM-69: persist the rejection reason on the existing venue booking request.
-- Must match VenueBooking.rejection_reason in app/models.py.
-- Additive and safe to re-run; existing rows keep NULL until rejected.
-- Run in the Supabase SQL editor as project owner before merging the model change.
-- For an existing LOCAL test database, apply this SQL explicitly: create_all()
-- does not add columns to existing tables. No new tables, so test_role.sql does
-- not need to be re-run.

begin;

alter table public.venue_bookings
  add column if not exists rejection_reason text;

commit;
