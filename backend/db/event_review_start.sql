-- Adds what SCRUM-31's reopened criteria (starting a review) need to events.
-- Must match Event in app/models.py; `test_database_tables_match_the_models` (and CI's
-- supabase-schema job) checks this.
--
-- review_started_at:     when the coordinator started the review (naive UTC).
-- review_started_by_id:  the coordinator who started it.
-- Both start empty, so existing requests are unchanged; a request under review from
-- before this script simply has no start recorded.
--
-- Run once in the Supabase SQL editor as the project owner. No new tables, so
-- db/test_role.sql need not be re-run. Safe to re-run.

begin;

alter table public.events
  add column if not exists review_started_at     timestamp,  -- UTC, no time zone
  add column if not exists review_started_by_id  integer references public.users (id);

commit;
