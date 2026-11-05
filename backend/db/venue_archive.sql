-- CF08 (Venue catalogue: Venue Staff can delete venue records): a venue is deleted by
-- archiving it. Must match Venue in app/models.py; `test_database_tables_match_the_models`
-- checks the columns.
--
-- venues.archived_at  when (naive UTC) the venue was archived; NULL for a venue in use.
-- An archived venue leaves the catalogue, venue search and new bookings. Its row, its
-- bookings and its history are kept, so nothing that refers to it breaks. Who archived or
-- restored it is a venue_changes row (action 'archived' or 'restored'), which fits the
-- existing varchar(10) column.
--
-- Run once in the Supabase SQL editor as the project owner. No new table, so
-- db/test_role.sql does not need to be re-run. Safe to re-run.

begin;

alter table public.venues add column if not exists archived_at timestamp;

commit;
