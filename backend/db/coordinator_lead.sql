-- Records who made each event's current coordinator assignment, for SCRUM-83 (Event
-- Coordinator Lead views the events they assigned). Must match Event in
-- app/models.py; `test_database_tables_match_the_models` checks this.
--
-- Existing rows are not changed: their assigner stays empty ("not recorded"), so they
-- appear in no Lead's list (assumption A1 in
-- docs/test-cases/SCRUM-83-lead-assigned-events.md, open question Q1). The new
-- `coordinator_lead` role needs no change here: users.role is plain text.
--
-- Run once in the Supabase SQL editor as the project owner. The test role already
-- has access to the events table, so db/test_role.sql need not be re-run.
-- Safe to re-run.

begin;

alter table public.events
  add column if not exists coordinator_assigned_by_id integer references public.users (id);

commit;
