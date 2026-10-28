-- Records the coordinator's decision on a change request, for SCRUM-70 (Review change
-- request to a submitted event). Must match EventChangeRequest in app/models.py;
-- `test_database_tables_match_the_models` checks this.
--
-- A request is 'pending_review' until the event's coordinator accepts or rejects it
-- (status 'accepted' or 'rejected'). These columns say when (UTC) and by whom, and why it
-- was rejected (working assumptions A4 and A5 in
-- docs/test-cases/SCRUM-70-review-change-request.md). All are NULL while it is pending.
--
-- Run once in the Supabase SQL editor as the project owner, after
-- db/event_change_requests.sql. No new tables, so db/test_role.sql need not be re-run.
-- Safe to re-run.

begin;

alter table public.event_change_requests
  add column if not exists decided_at      timestamp,  -- UTC, no time zone
  add column if not exists decided_by_id   integer references public.users (id),
  add column if not exists decision_reason text;

commit;
