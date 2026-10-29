-- SCRUM-93: confirmation audit fields on Event; must match app/models.py.
-- Run in the Supabase SQL editor as project owner before merging/deploying.
-- Existing events remain unconfirmed (NULL audit fields). No new tables;
-- test_role.sql does not need to be re-run.

begin;

alter table public.events
  add column if not exists confirmed_by_id integer references public.users (id),
  add column if not exists confirmed_at timestamp; -- UTC, no time zone

commit;
