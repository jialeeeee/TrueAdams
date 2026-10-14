-- Adds what SCRUM-39 (Submit a Venue Booking Request) needs to venue_bookings.
-- Must match VenueBooking in app/models.py; `test_database_tables_match_the_models`
-- checks this.
--
-- venue_requirements: what Venue Staff assess the request against.
-- requested_by_id:    the coordinator who made the request.
-- Both start empty, so existing bookings are unchanged.
--
-- An event may have at most one pending venue request (assumption A6 in
-- docs/test-cases/SCRUM-39-venue-booking-request.md, open question Q6).
--
-- Run once in the Supabase SQL editor as the project owner. No new tables, so
-- db/test_role.sql need not be re-run. Safe to re-run.

begin;

alter table public.venue_bookings
  add column if not exists venue_requirements  text,
  add column if not exists requested_by_id     integer references public.users (id);

-- Stop with a clear message, rather than a bare index error, if existing rows
-- already break the one-pending-request rule.
do $$
begin
  if exists (
    select 1 from public.venue_bookings
    where status = 'pending' and event_id is not null
    group by event_id
    having count(*) > 1
  ) then
    raise exception 'Some events already have more than one pending venue booking. Resolve those rows, then run this script again.';
  end if;
end $$;

create unique index if not exists venue_bookings_one_pending_per_event
  on public.venue_bookings (event_id)
  where status = 'pending';

commit;
