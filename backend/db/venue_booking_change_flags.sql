-- SCRUM-70 AC10 (Review a change request): venue bookings flagged for the coordinator to
-- decide on because an accepted change request affects them. Must match
-- VenueBookingChangeFlag in app/models.py; `test_database_tables_match_the_models` checks
-- the columns.
--
-- venue_booking_change_flags: one row per flag, with the accepted change request that
--   raised it, why it affects the booking (a JSON list of sentences), who accepted the
--   change and when, and a status ("flagged" until the coordinator keeps the booking,
--   then "kept"). At most one open flag per booking. The booking row is never touched.
--
-- Run once in the Supabase SQL editor as the project owner. New table, so run
-- db/test_role.sql again too. Safe to re-run.

begin;

create table if not exists public.venue_booking_change_flags (
  id                 serial primary key,
  booking_id         integer     not null
                     references public.venue_bookings (id) on delete cascade,
  change_request_id  integer     not null references public.event_change_requests (id),
  reasons            jsonb       not null,
  status             varchar(20) not null default 'flagged',
  flagged_by_id      integer     references public.users (id),
  flagged_at         timestamp   not null default (now() at time zone 'utc'),
  decided_by_id      integer     references public.users (id),
  decided_at         timestamp
);

create unique index if not exists venue_booking_change_flags_one_open_per_booking
  on public.venue_booking_change_flags (booking_id) where status = 'flagged';

-- Row Level Security on with no policies blocks the Supabase API, like every other table.
alter table public.venue_booking_change_flags enable row level security;

commit;
