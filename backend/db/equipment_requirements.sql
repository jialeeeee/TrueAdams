-- Creates the equipment_requirements table for SCRUM-42 (Record equipment requirements
-- for an event). Must match EquipmentRequirement in app/models.py;
-- `test_database_tables_match_the_models` checks this.
--
-- One row per item an event needs: its type, quantity and technical requirements,
-- recorded by the event's coordinator, and the arrangement status and note that
-- Technical Support Staff update ('requested', 'being_arranged' or 'unavailable';
-- working assumption A7 in docs/test-cases/SCRUM-42-equipment-requirements.md).
-- Recording a requirement reserves nothing (AC5). The organiser's free-text
-- events.equipment_requirements (SCRUM-29) is left as it is (A2).
--
-- Run once in the Supabase SQL editor as the project owner, then re-run
-- db/test_role.sql so the test role can use the new table. Safe to re-run.

begin;

create table if not exists public.equipment_requirements (
  id                         serial primary key,
  event_id                   integer not null references public.events (id),
  equipment_type             varchar(100) not null,
  quantity                   integer not null
    constraint equipment_requirements_quantity_positive check (quantity > 0),
  technical_requirements     text,
  status                     varchar(20) not null default 'requested',
  arrangement_note           text,
  recorded_by_id             integer not null references public.users (id),
  recorded_at                timestamp not null default (now() at time zone 'utc'),  -- UTC, no time zone
  last_saved_at              timestamp not null default (now() at time zone 'utc'),
  arrangement_updated_by_id  integer references public.users (id),
  arrangement_updated_at     timestamp
);

create index if not exists equipment_requirements_event_id
  on public.equipment_requirements (event_id);

-- Match the other public tables: RLS on, so the Supabase API is blocked by default.
alter table public.equipment_requirements enable row level security;

commit;
