-- SCRUM-98 (Coordinator cancels an event): who cancelled an event, when and why. Must
-- match Event in app/models.py; `test_database_tables_match_the_models` checks the columns.
--
-- events.cancelled_by_id      the coordinator who cancelled it
-- events.cancelled_at         when, naive UTC like the other audit timestamps
-- events.cancellation_reason  the reason they gave (at most 500 characters, checked by the app)
-- All NULL for an event that hasn't been cancelled. The status `cancelled` already exists.
--
-- Run once in the Supabase SQL editor as the project owner. No new table, so
-- db/test_role.sql does not need to be re-run. Safe to re-run.

begin;

alter table public.events
  add column if not exists cancelled_by_id integer references public.users (id),
  add column if not exists cancelled_at timestamp,
  add column if not exists cancellation_reason text;

commit;
