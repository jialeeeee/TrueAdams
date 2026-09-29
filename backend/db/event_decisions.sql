-- Adds the coordinator's decision to the events table for SCRUM-32 (Approve or
-- Reject an Event Request). Must match Event in app/models.py;
-- `test_database_tables_match_the_models` checks this.
--
-- Existing rows are not changed: every new column starts empty.
--
-- Run once in the Supabase SQL editor as the project owner. The test role already
-- has access to the events table, so db/test_role.sql need not be re-run.
-- Safe to re-run.

begin;

alter table public.events
  add column if not exists decision_note  text,       -- rejection reason / approval note
  add column if not exists decided_at     timestamp,  -- UTC, no time zone
  add column if not exists decided_by_id  integer references public.users (id);

commit;
