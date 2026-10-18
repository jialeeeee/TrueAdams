-- Removes the waiting list, for SCRUM-45 (Register for an Event), reopened on 18 Oct 2026:
-- a full event is now blocked with "This event is full." and nobody is waitlisted. Must
-- match Event and Registration in app/models.py; `test_database_tables_match_the_models`
-- checks the columns.
--
-- 1. Any 'waitlisted' registrations become 'cancelled'. They never held a place, and
--    nothing promotes them any more (SCRUM-68 no longer does).
-- 2. The one-active-registration index now counts 'registered' rows only.
-- 3. events.waitlist_enabled is dropped; no code reads it.
--
-- Run once in the Supabase SQL editor as the project owner, after
-- db/event_registration.sql. No new tables, so db/test_role.sql need not be re-run.
-- Safe to re-run.

begin;

update public.registrations set status = 'cancelled' where status = 'waitlisted';

drop index if exists public.registrations_one_active_per_attendee;
create unique index registrations_one_active_per_attendee
  on public.registrations (event_id, attendee_id)
  where status = 'registered';

alter table public.events drop column if exists waitlist_enabled;

commit;
