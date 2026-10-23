-- Creates the equipment_reservations table for SCRUM-44 (Reserve equipment for an
-- event). Must match EquipmentReservation in app/models.py;
-- `test_database_tables_match_the_models` checks this.
--
-- One row per item of equipment (resources) and quantity that Technical Support Staff
-- reserved for one of an event's equipment requirements, over the event's period
-- (Singapore time without a time zone, half-open [start, end)). Only rows with status
-- 'reserved' hold equipment; a released row is kept as history, with when and why
-- (working assumption A10 in docs/test-cases/SCRUM-44-reserve-equipment.md). When the
-- requirement is removed, requirement_id becomes NULL and the row stays.
--
-- Run once in the Supabase SQL editor as the project owner, then re-run
-- db/test_role.sql so the test role can use the new table. Safe to re-run.

begin;

create table if not exists public.equipment_reservations (
  id              serial primary key,
  event_id        integer not null references public.events (id),
  requirement_id  integer references public.equipment_requirements (id) on delete set null,
  resource_id     integer not null references public.resources (id),
  quantity        integer not null,
  start_time      timestamp not null,  -- Singapore time, no time zone
  end_time        timestamp not null,
  status          varchar(20) not null default 'reserved',  -- 'reserved' or 'released'
  reserved_by_id  integer not null references public.users (id),
  reserved_at     timestamp not null default (now() at time zone 'utc'),  -- UTC, no time zone
  released_at     timestamp,
  release_reason  text,
  constraint equipment_reservations_quantity_positive check (quantity > 0),
  constraint equipment_reservations_end_after_start check (end_time > start_time)
);

create index if not exists equipment_reservations_event_id
  on public.equipment_reservations (event_id);
create index if not exists equipment_reservations_requirement_id
  on public.equipment_reservations (requirement_id);
create index if not exists equipment_reservations_resource_id
  on public.equipment_reservations (resource_id);

-- Match the other public tables: RLS on, so the Supabase API is blocked by default.
alter table public.equipment_reservations enable row level security;

commit;
