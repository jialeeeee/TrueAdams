# CF08 — Venue Staff delete (archive) a venue record: Test Cases

**Requirement:** CF08 Venue catalogue: "Venue Staff can create, edit and delete venue records." SCRUM-63 covers adding and editing; this covers deleting. *No Jira story exists for it yet; add one to the backlog (for example "Venue Staff archive a venue") before marking it Done.*

**Created:** 4 Nov 2026 · **Status of all cases:** automated cases pass (4 Nov 2026, local PostgreSQL as in CI + Vitest) · **Automated tests:** `backend/tests/test_venue_archive.py`, `frontend/src/pages/VenueArchive.test.jsx` · **Endpoints:** `POST /api/venues/<id>/archive`, `POST /api/venues/<id>/restore`, and `GET /api/venues/?archived=include` · **Related:** SCRUM-63 (catalogue and its change history), SCRUM-37 (search), SCRUM-39 (venue requests), SCRUM-88 (recording a venue as unavailable)

## Criteria (proposed, to agree)

| ID | Criterion |
|----|-----------|
| C1 | Venue Staff can delete a venue from the catalogue. It is then not listed, not offered by venue search and can't be requested, but its record, bookings and history are kept. |
| C2 | A venue with bookings still to come can't be deleted, and Venue Staff are told why and what to do instead. |
| C3 | Venue Staff can undo a deletion. |
| C4 | Only Venue Staff can delete or undo. Anyone else is denied and nothing changes. |
| C5 | Each deletion and undo records who and when; a failed save changes nothing and says so. |

## Working assumptions (team decision, 4 Nov 2026)

- **A1 — Deleting is archiving (C1):** six tables refer to a venue (events, bookings, two kinds of booking flags, unavailable periods, change history), so removing the row would either fail or erase planning history. Archiving sets `venues.archived_at` (`db/venue_archive.sql`). An archived venue is left out of `GET /api/venues/` and venue search (and so of every page that picks a venue from them), a venue request for it is refused (409 `archived`), and editing it is refused until it is restored (409 `archived`). Its details, availability and history can still be read, and its payloads gain `archived_at`. Venue Staff list archived venues with `?archived=include`; for anyone else the parameter changes nothing.
- **A2 — Upcoming bookings (C2):** refused with 409 `upcoming_bookings` (and the booking IDs) while the venue has a pending, tentative (unexpired hold) or confirmed booking that hasn't ended. The message says to record the venue as unavailable (SCRUM-88), which flags confirmed bookings for replacement and warns coordinators, or to archive it once they are over. *(Q1)*
- **A3 — Restoring (C3):** `POST /api/venues/<id>/restore` clears `archived_at`; the venue is back in the catalogue and can be edited. Archiving an archived venue or restoring one in use is 409.
- **A4 — Who (C4):** Venue Staff, as main or additional role (CF01). Order of checks: 401 → 404 → 403 → 409 → 503.
- **A5 — Record and failures (C5):** each archive or restore adds a `venue_changes` row (`archived` / `restored`) with who and when, shown in the venue's change history, in the same commit. A failed save is 503 `retryable` and changes nothing.

## Test cases

| ID | Traces to | What it checks | Automated |
|----|-----------|----------------|-----------|
| TC-CF08-01 | C1, C5 | Archived with the time and a history row; gone from everyone's catalogue; Venue Staff can list it with `?archived=include`, a coordinator can't | `test_tc_cf08_01_archiving_removes_the_venue_from_the_catalogue`, `test_tc_cf08_01_venue_staff_can_list_archived_venues` |
| TC-CF08-02 | C1 | Venue search offers it before, not after | `test_tc_cf08_02_an_archived_venue_is_not_offered_by_search` |
| TC-CF08-03 | C1 | A venue request for it: 409 `archived`, nothing created; editing: 409 `archived`, unchanged | `test_tc_cf08_03_an_archived_venue_cannot_be_requested_or_edited` |
| TC-CF08-04 | C1 | Its details, past bookings and history are kept and readable | `test_tc_cf08_04_its_records_are_kept_and_still_readable` |
| TC-CF08-05 | C2 | A confirmed, pending or unexpired tentative booking still to come: 409 `upcoming_bookings` with its ID and "Record it as unavailable"; several are counted; ended, rejected, cancelled, replaced, expired bookings and other venues' bookings don't count | `test_tc_cf08_05_*` (3 tests) |
| TC-CF08-06 | C4 | 401 (no token, deleted user), 404, 403 for a coordinator, organiser and Technical Support, nothing recorded; Venue Staff as an additional role may | `test_tc_cf08_06_who_may_archive_and_restore_and_in_what_order`, `test_tc_cf08_06_an_additional_venue_staff_role_is_enough` |
| TC-CF08-07 | C3, C5 | Restoring puts it back, records who and when, and it can be edited; archiving twice or restoring a venue in use is 409 | `test_tc_cf08_07_restoring_puts_the_venue_back`, `test_tc_cf08_07_archiving_twice_or_restoring_a_venue_in_use_is_refused` |
| TC-CF08-08 | C5 | A failed archive or restore is 503 `retryable` and changes nothing | `test_tc_cf08_08_a_failed_archive_or_restore_changes_nothing` |
| TC-CF08-09 | C1 | The edit page archives after a confirmation step, shows it archived with no Save, and the history says "Archived"; "Back" archives nothing | frontend "archives the venue after a confirmation step", "backing out archives nothing" |
| TC-CF08-10 | C2, C5 | A refusal or failure is explained | frontend "explains why a venue can't be archived" |
| TC-CF08-11 | C3, C4 | Restoring from the edit page; a failed restore explained; Venue Staff can show archived venues on the list, marked "(archived)"; nobody else is offered it | frontend "restores an archived venue", "explains a failed restore", "lets Venue Staff show archived venues, marked as archived", "offers nobody else archived venues" |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Should deleting a venue with bookings still to come be allowed, flagging them for replacement as SCRUM-88 does (as built: refused until they are over or moved)? | A2, TC-CF08-05 |
| Q2 | Should a deleted venue ever be removed for good, for example after some years? | A1 |

## Before merging

Run `backend/db/venue_archive.sql` in the Supabase SQL editor as the project owner. It adds a column only, so `db/test_role.sql` doesn't need to be run again. It is safe to re-run. The CI `supabase-schema` job fails until it has been run.
