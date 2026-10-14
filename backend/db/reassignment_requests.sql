-- Creates the reassignment_requests table for SCRUM-61 (Request Event Coordinator
-- reassignment). Must match ReassignmentRequest in app/models.py;
-- `test_database_tables_match_the_models` checks this.
--
-- A request names the event, the coordinator asking (requester_id), the coordinator
-- asked to take over (coordinator_id) and the reason. Its status is 'pending' until a
-- later story accepts or declines it. An event can have at most one pending request
-- (working assumption A6 in docs/test-cases/SCRUM-61-reassignment-request.md).
--
-- Run once in the Supabase SQL editor as the project owner, then re-run
-- db/test_role.sql so the test role can use the new table. Safe to re-run.

begin;

create table if not exists public.reassignment_requests (
  id              serial primary key,
  event_id        integer not null references public.events (id),
  requester_id    integer not null references public.users (id),
  coordinator_id  integer not null references public.users (id),
  reason          text not null,
  status          varchar(20) not null default 'pending',
  requested_at    timestamp not null default (now() at time zone 'utc')  -- UTC, no time zone
);

create unique index if not exists reassignment_requests_one_pending_per_event
  on public.reassignment_requests (event_id)
  where status = 'pending';

-- Match the other public tables: RLS on, so the Supabase API is blocked by default.
alter table public.reassignment_requests enable row level security;

commit;
