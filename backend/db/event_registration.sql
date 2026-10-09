-- Adds what SCRUM-45 (Register for an Event) needs. Must match Event and
-- Registration in app/models.py; `test_database_tables_match_the_models` checks this.
--
-- events: the registration period (Singapore time, like the event's own times), the
-- number of places, and whether there is a waiting list. Every new column starts
-- empty, and NULL means not recorded, so existing events stay closed to registration.
--
-- registrations: a status ('registered', 'waitlisted' or 'cancelled'). Existing rows
-- become 'registered', so they stay active. An attendee may have at most one active
-- (registered or waitlisted) registration per event.
--
-- These follow working assumptions A3-A7 in
-- docs/test-cases/SCRUM-45-register-for-event.md (open questions Q3-Q7).
--
-- Run once in the Supabase SQL editor as the project owner. No new tables, so
-- db/test_role.sql need not be re-run. Safe to re-run.

begin;

alter table public.events
  add column if not exists registration_opens_at   timestamp,  -- Singapore time, no time zone
  add column if not exists registration_closes_at  timestamp,  -- Singapore time, no time zone
  add column if not exists registration_capacity   integer,
  add column if not exists waitlist_enabled        boolean;

alter table public.registrations
  add column if not exists status  varchar(20) not null default 'registered';

-- Stop with a clear message, rather than a bare index error, if existing rows
-- already break the one-active-registration rule.
do $$
begin
  if exists (
    select 1 from public.registrations
    where status in ('registered', 'waitlisted')
    group by event_id, attendee_id
    having count(*) > 1
  ) then
    raise exception 'Some attendees already have more than one active registration for the same event. Resolve those rows, then run this script again.';
  end if;
end $$;

create unique index if not exists registrations_one_active_per_attendee
  on public.registrations (event_id, attendee_id)
  where status in ('registered', 'waitlisted');

commit;
