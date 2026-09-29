-- Changes the events table for SCRUM-29 (Save and Resume a Draft Event Request).
-- Must match Event in app/models.py; `test_database_tables_match_the_models`
-- checks this.
--
-- Drafts may leave the proposed dates empty, so start_time and end_time become
-- nullable; submission still requires them (enforced by the app). Existing rows
-- are not changed: every new column starts empty.
--
-- Run once in the Supabase SQL editor as the project owner. The test role already
-- has access to the events table, so db/test_role.sql need not be re-run.
-- Safe to re-run.

begin;

alter table public.events
  alter column start_time drop not null,
  alter column end_time drop not null,
  add column if not exists purpose                 text,
  add column if not exists expected_attendance     integer,
  add column if not exists venue_requirements      text,
  add column if not exists accessibility_needs     text,
  add column if not exists equipment_requirements  text,
  add column if not exists registration_required   boolean,
  add column if not exists last_saved_at           timestamp,  -- UTC, no time zone
  add column if not exists submitted_at            timestamp;  -- UTC, no time zone

-- An organiser's drafts are listed most recently saved first.
create index if not exists events_organiser_status_saved
  on public.events (organiser_id, status, last_saved_at);

commit;
