-- Adds what SCRUM-38 (Assess a Venue Against Event Requirements) needs to events.
-- Must match Event in app/models.py; `test_database_tables_match_the_models` checks this.
--
-- required_facilities, required_accessibility_features, required_layouts: what the
-- event needs of a venue, as JSON lists of names. NULL means not recorded (the venue
-- check shows "Unable to assess"); an empty list means the event needs none.
-- All start empty, so existing events are unchanged.
--
-- Run once in the Supabase SQL editor as the project owner. No new tables, so
-- db/test_role.sql need not be re-run. Safe to re-run.

begin;

alter table public.events
  add column if not exists required_facilities              jsonb,
  add column if not exists required_accessibility_features  jsonb,
  add column if not exists required_layouts                 jsonb;

commit;
