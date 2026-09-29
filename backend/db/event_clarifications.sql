-- Creates the event_clarifications and notifications tables for SCRUM-31 (Review
-- and Request Clarification on an Event Request). Must match EventClarification
-- and Notification in app/models.py; `test_database_tables_match_the_models`
-- checks this.
--
-- Run once in the Supabase SQL editor as the project owner, then re-run
-- db/test_role.sql so the test role can use the new tables. Safe to re-run.

begin;

create table if not exists public.event_clarifications (
  id          serial primary key,
  event_id    integer not null references public.events (id),
  sender_id   integer not null references public.users (id),
  message     text not null,
  created_at  timestamp  -- UTC, no time zone
);

create table if not exists public.notifications (
  id            serial primary key,
  recipient_id  integer not null references public.users (id),
  kind          varchar(50) not null,
  message       text not null,
  event_id      integer references public.events (id),
  created_at    timestamp,  -- UTC, no time zone
  read_at       timestamp
);

-- An event's questions are listed oldest first; a user's notifications newest first.
create index if not exists event_clarifications_event_time
  on public.event_clarifications (event_id, created_at);
create index if not exists notifications_recipient_time
  on public.notifications (recipient_id, created_at);

-- Match the other public tables: RLS on, so the Supabase API is blocked by default.
alter table public.event_clarifications enable row level security;
alter table public.notifications enable row level security;

commit;
