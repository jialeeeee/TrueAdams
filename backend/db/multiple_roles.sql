-- CF01 (SCRUM-76, G4 clarification #22): a user may hold more than one role. Adds
-- User.additional_roles (app/models.py): the roles a user holds besides users.role, as a
-- JSON list of role names. NULL means none, so every existing user keeps exactly the role
-- they have now.
-- Run in the Supabase SQL editor as the project owner before merging. No new table;
-- test_role.sql does not need to be re-run (it already grants access to users).

begin;

alter table public.users
  add column if not exists additional_roles jsonb;

commit;
