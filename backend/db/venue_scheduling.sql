-- Creates the venue_bookings and venue_blocks tables for SCRUM-36 (venue
-- availability) and SCRUM-37 (venue search). Must match VenueBooking and
-- VenueBlock in app/models.py; `test_database_tables_match_the_models` checks this.
--
-- Run once in the Supabase SQL editor as the project owner, then re-run
-- db/test_role.sql so the test role can use the new tables. Safe to re-run.

begin;

create table if not exists public.venue_bookings (
  id          serial primary key,
  venue_id    integer not null references public.venues (id),
  event_id    integer references public.events (id),
  status      varchar(20) not null default 'pending',
  start_time  timestamp not null,  -- Singapore time, no time zone
  end_time    timestamp not null,
  created_at  timestamp,
  constraint venue_bookings_end_after_start check (end_time > start_time)
);

create table if not exists public.venue_blocks (
  id          serial primary key,
  venue_id    integer not null references public.venues (id),
  reason      text,
  start_time  timestamp not null,  -- Singapore time, no time zone
  end_time    timestamp not null,
  created_at  timestamp,
  constraint venue_blocks_end_after_start check (end_time > start_time)
);

-- Availability and search look bookings and blocks up by venue and time.
create index if not exists venue_bookings_venue_time
  on public.venue_bookings (venue_id, start_time, end_time);
create index if not exists venue_blocks_venue_time
  on public.venue_blocks (venue_id, start_time, end_time);

-- Match the other public tables: RLS on, so the Supabase API is blocked by default.
alter table public.venue_bookings enable row level security;
alter table public.venue_blocks enable row level security;

commit;
