-- Creates the equipment_unavailability table for SCRUM-43 (Check equipment
-- availability for an event). Must match EquipmentUnavailability in app/models.py;
-- `test_database_tables_match_the_models` checks this.
--
-- A recorded period when an item in the equipment catalogue (resources) can't be used,
-- e.g. repair, with a reason. Times are Singapore time without a time zone, half-open
-- [start, end). An item with a period overlapping an event is excluded from that
-- event's availability check as a whole (working assumption A5 in
-- docs/test-cases/SCRUM-43-equipment-availability.md).
--
-- Run once in the Supabase SQL editor as the project owner, then re-run
-- db/test_role.sql so the test role can use the new table. Safe to re-run.

begin;

create table if not exists public.equipment_unavailability (
  id           serial primary key,
  resource_id  integer not null references public.resources (id),
  start_time   timestamp not null,  -- Singapore time, no time zone
  end_time     timestamp not null,
  reason       text,
  created_at   timestamp default (now() at time zone 'utc'),  -- UTC, no time zone
  constraint equipment_unavailability_end_after_start check (end_time > start_time)
);

create index if not exists equipment_unavailability_resource_id
  on public.equipment_unavailability (resource_id);

-- Match the other public tables: RLS on, so the Supabase API is blocked by default.
alter table public.equipment_unavailability enable row level security;

commit;
