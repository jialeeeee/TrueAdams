-- Creates the event_change_requests table for SCRUM-46 (Submit change request for a
-- submitted event). Must match EventChangeRequest in app/models.py;
-- `test_database_tables_match_the_models` checks this.
--
-- A request names the event, the organiser who asked (requested_by_id), when, and each
-- field that would change with its current and proposed value (changes). Its status is
-- 'pending_review' until a later story decides it. An event can have at most one request
-- pending review (working assumption A6 in docs/test-cases/SCRUM-46-change-request.md).
--
-- Run once in the Supabase SQL editor as the project owner, then re-run
-- db/test_role.sql so the test role can use the new table. Safe to re-run.

begin;

create table if not exists public.event_change_requests (
  id               serial primary key,
  event_id         integer not null references public.events (id),
  requested_by_id  integer not null references public.users (id),
  status           varchar(20) not null default 'pending_review',
  changes          jsonb not null,
  requested_at     timestamp not null default (now() at time zone 'utc')  -- UTC, no time zone
);

create unique index if not exists event_change_requests_one_pending_per_event
  on public.event_change_requests (event_id)
  where status = 'pending_review';

-- Match the other public tables: RLS on, so the Supabase API is blocked by default.
alter table public.event_change_requests enable row level security;

commit;
