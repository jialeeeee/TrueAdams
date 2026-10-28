-- SCRUM-91: separate safety approval on Event; must match app/models.py.
-- Run in the Supabase SQL editor as project owner before deploying this model.
-- Existing events start with no safety decision. Idempotent; no new tables,
-- so test_role.sql does not need to be re-run.

begin;

alter table public.events
  add column if not exists safety_decision      varchar(20),
  add column if not exists safety_decided_by_id integer references public.users (id),
  add column if not exists safety_comment       text,
  add column if not exists safety_decided_at    timestamp; -- UTC, no time zone

commit;
