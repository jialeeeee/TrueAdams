-- SCRUM-41 (Prevent Conflicting Venue Bookings): the database refuses to store two
-- confirmed bookings at the same venue whose periods overlap, even when they are
-- saved by code that does not lock the venue (assumption A4 in
-- docs/test-cases/SCRUM-41-prevent-venue-booking-conflicts.md, open question Q3).
-- Must match venue_bookings_no_overlapping_confirmed in VenueBooking.__table_args__
-- (app/models.py).
--
-- Periods are half-open: tsrange(start, end) includes the start but not the end, so
-- bookings that only touch are allowed. The venue id is written as a one-value range,
-- int4range(id, id, '[]'), so a plain GiST index can compare it without an extension.
--
-- Run once in the Supabase SQL editor as the project owner. No new tables or columns,
-- so db/test_role.sql need not be re-run. Safe to re-run.

begin;

do $$
begin
  -- Stop with a clear message, rather than a bare constraint error, if existing rows
  -- already break the rule.
  if exists (
    select 1
    from public.venue_bookings a
    join public.venue_bookings b
      on a.venue_id = b.venue_id
     and a.id < b.id
     and a.start_time < b.end_time
     and b.start_time < a.end_time
    where a.status = 'confirmed' and b.status = 'confirmed'
  ) then
    raise exception 'Some venues already have overlapping confirmed bookings. Resolve those rows, then run this script again.';
  end if;

  if not exists (
    select 1 from pg_constraint where conname = 'venue_bookings_no_overlapping_confirmed'
  ) then
    alter table public.venue_bookings
      add constraint venue_bookings_no_overlapping_confirmed
      exclude using gist (
        int4range(venue_id, venue_id, '[]') with &&,  -- the same venue
        tsrange(start_time, end_time) with &&         -- overlapping [start, end)
      )
      where (status = 'confirmed');
  end if;
end $$;

commit;
