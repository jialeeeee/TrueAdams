-- SCRUM-75 AC6 (Sign in and sign out): the access tokens users signed out of, so the API
-- refuses them until they expire. Must match RevokedToken in app/models.py;
-- `test_database_tables_match_the_models` checks the columns.
--
-- revoked_tokens: one row per signed-out token, by its unique JWT ID (jti), with its user,
--   when they signed out and when the token would have expired (both naive UTC). Rows past
--   expires_at can be deleted at any time.
--
-- Run once in the Supabase SQL editor as the project owner. New table, so run
-- db/test_role.sql again too. Safe to re-run.

begin;

create table if not exists public.revoked_tokens (
  id          serial primary key,
  jti         varchar(64) not null unique,
  user_id     integer     not null references public.users (id) on delete cascade,
  revoked_at  timestamp   not null default (now() at time zone 'utc'),
  expires_at  timestamp
);

-- Row Level Security on with no policies blocks the Supabase API, like every other table.
alter table public.revoked_tokens enable row level security;

commit;
