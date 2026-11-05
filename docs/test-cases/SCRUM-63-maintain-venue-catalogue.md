# SCRUM-63 — Maintain the Venue Catalogue: Test Cases

**User story:** As Venue Staff, I want to add and edit venues in the catalogue, so that coordinators always see accurate venue information.

**Created:** 20 Oct 2026 · **Source of the cases:** the "Sprint 3 test cases" tab of the ConnectSphere Backlog to Feature Map sheet (IS212-US63-TC1 to TC16; TC17 to TC27 for the AC9 reopen are on the "Sprint 4 test cases" tab) · **Automated tests:** `backend/tests/test_venue_catalogue.py`, `frontend/src/pages/VenueFormPage.test.jsx` · **Status:** TC1-TC16 pass locally (20 Oct 2026); TC17-TC27 (AC9) written test-first on 31 Oct 2026; TC13's "stop the database" variant and the browser walk-through are still to be run by hand.

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | Venue Staff can add a venue with its name, location, capacity, facilities, accessibility features, supported layouts and operating hours. |
| AC2 | Name, location and capacity are required, and capacity must be a whole number of at least 1. |
| AC3 | Facilities, accessibility features and layouts are chosen from defined lists, so they can be used as search filters. |
| AC4 | Venue Staff can edit an existing venue's information, and the changes appear in the venue details when reopened. |
| AC5 | Invalid entries prevent saving, the fields needing correction are identified, and entered information is kept. |
| AC6 | If saving fails for another reason, Venue Staff are informed, previously saved information is unchanged, and their edits are kept for retry. |
| AC7 | Each change to a venue records who made it and when. |
| AC8 | Only Venue Staff can add or edit venues. |
| AC9 | Venue Staff can set a setup time and a turnaround time for each venue, in whole minutes from 0 to 1440. A venue with none set uses 0. *(Added when the story was reopened, 31 Oct 2026.)* |

## Working assumptions (to confirm)

- **A1 — Endpoints:** `POST /api/venues/` adds, `PUT /api/venues/<id>` edits (only the fields sent change), `GET /api/venues/options` gives the defined lists, `GET /api/venues/<id>/history` gives the change history. All are Venue Staff only (role read from the database, 403 otherwise).
- **A2 — Order of checks:** 401, 403, 404, 400 (every invalid field at once, in `fields`), then a database failure is 503 `retryable`. Nothing is saved on any failure.
- **A3 — The defined lists are those in the test cases:** facilities Projector, Microphone, Video conferencing; accessibility features Wheelchair ramp, Hearing loop; layouts Theatre, Classroom, Boardroom, Banquet. Layouts are stored in the lower-case keys venue search already uses. **Open question:** the customer has not given the full lists; existing seed venues use other values (e.g. Stage, Wi-Fi), which stay as they are but can't be chosen for new venues.
- **A4 — Operating hours** are optional. When given they must be in the form the availability calendar understands (e.g. `Mon-Fri 08:00-22:00`); empty means "not recorded".
- **A5 — Change history:** one `venue_changes` row per add or edit, in the same commit as the change, with a from/to for each field touched. An edit that changes nothing records nothing.
- **A6 — Add/Edit buttons** are shown only when `GET /venues/options` succeeds, so the screen never decides roles itself.
- **A7 — Out of scope:** deleting or disabling a venue; contact details, description, area, parking and catering (not in AC1).
- **A8 — AC9 fields (reopened story):** `setup_minutes` and `turnaround_minutes` on the venue, sent with the same `POST`/`PUT` as the other fields and validated like them (all invalid fields named at once, nothing saved on a refusal). A value is a whole number from 0 to 1440 (`MAX_BUFFER_MINUTES`); `30`, `30.0` and `"30"` are accepted, `30.5`, `abc`, `true`, a list, `-1` and `1441` are not.
- **A9 — "None set" is NULL:** a venue that has never had a value, or that has had one cleared (`null` or empty text), stores NULL, shows as *not recorded* in the details and counts as 0 minutes everywhere it is used (`scheduling.buffers(venue)`). A recorded `0` is kept as 0 and is not "not recorded" (AGENTS.md "NULL means not recorded"). **Open question Q8:** whether the screen should show 0 or an empty box for a venue with none set; the tests only rely on it being treated as 0.
- **A10 — Who can see them:** the values are part of the venue details, so any role that can open venue details sees them; only Venue Staff can change them (AC8), and every change is in the venue's history (AC7) like any other field.
- **A11 — Booking-level behaviour is SCRUM-84's:** TC24's occupied period (a booking at a venue with none set occupies exactly its event time) is asserted in `test_venue_setup_turnaround.py` on the SCRUM-84 branch; here TC24 checks that the venue reports none set and that the scheduling value is 0.

## Test cases

| Sheet ID | Automated by | What it checks |
|----------|--------------|----------------|
| TC1 | `test_tc1_add_venue_with_every_detail`; frontend TC1 | All seven fields stored and shown again on reopen |
| TC2 | `test_tc2_name_is_required` | Missing/blank name rejected, nothing created |
| TC3 | `test_tc3_location_is_required` | Missing location rejected |
| TC4 | `test_tc4_capacity_is_required` | Missing capacity rejected |
| TC5 | `test_tc5_capacity_of_one_is_accepted` | Lower boundary accepted |
| TC6 | `test_tc6_capacity_of_zero_is_rejected` (+ negative) | Capacity below 1 rejected with the stated message |
| TC7 | `test_tc7_capacity_that_is_not_a_whole_number_is_rejected` | 50.5, text, true, list rejected |
| TC8 | `test_tc8_options_are_the_defined_lists`; frontend TC8 | Only listed options offered, no free text |
| TC9 | `test_tc9_value_outside_a_defined_list_is_rejected` | Direct API call with "Jacuzzi" rejected, error names Facilities |
| TC10 | `test_tc10_saved_facility_works_as_a_search_filter` | Saved facility found by venue search |
| TC11 | `test_tc11_edit_shows_when_reopened_and_leaves_the_rest`; frontend TC11 | Edit shows on reopen, other fields unchanged |
| TC12 | `test_tc12_every_invalid_field_is_named_in_one_reply`; frontend TC2-4/6/12 | Several invalid fields named at once, entries kept |
| TC13 | `test_tc13_failed_edit_changes_nothing_and_can_be_retried`; frontend TC13 | 503 retryable, stored value unchanged, retry succeeds, form keeps the edit |
| TC14 | `test_tc14_add_and_edit_record_who_and_when` | Two entries, right users, times within a minute |
| TC15 | `test_tc15_coordinator_cannot_add_or_edit`; frontend TC15 | 403 on API, no actions shown, refusal on direct URL |
| TC16 | `test_tc16_attendee_cannot_add` | 403, nothing created |

### AC9 (reopened): sheet IS212-US63-TC17 to TC27

| Sheet ID | Automated by | What it checks |
|----------|--------------|----------------|
| TC17 | `test_tc17_set_setup_and_turnaround_and_see_them_on_reopen` | 30 and 45 saved and shown on reopen |
| TC18 | `test_tc18_zero_is_accepted_and_kept_as_zero_not_blank` | 0 and 0 accepted, shown as 0 (not "not recorded") |
| TC19 | `test_tc19_1440_is_accepted` | Upper boundary accepted |
| TC20 | `test_tc20_setup_of_1441_is_rejected` | Setup 1441 rejected, field named, stored value kept |
| TC21 | `test_tc21_turnaround_of_1441_is_rejected` | Turnaround 1441 rejected, field named, stored value kept |
| TC22 | `test_tc22_negative_minutes_are_rejected` | -1 rejected for each field |
| TC23 | `test_tc23_values_that_are_not_whole_numbers_are_rejected` | 30.5, abc, true and a list rejected |
| TC24 | `test_tc24_a_venue_with_none_set_uses_zero` (+ values-set variant) | NULL shown as not recorded, treated as 0; booking-level part is on the SCRUM-84 branch (A11) |
| TC25 | `test_tc25_out_of_range_value_sent_directly_is_rejected` | Direct `PUT` with 1441: error names the setup time, nothing saved, no history entry |
| TC26 | `test_tc26_coordinator_cannot_set_setup_or_turnaround` (+ read-only variant); frontend TC26 | 403 for coordinator and attendee, values unchanged; coordinator can still read; no edit fields on screen |
| TC27 | `test_tc27_changing_the_turnaround_records_who_and_when` | History entry by venue_staff2 with from 45 to 60, within a minute |

Extra AC9 cases: a venue added with both values, numeric text accepted, clearing a value, editing other fields leaves them alone, a bad setup time is named with other invalid fields.

Extra cases beyond the sheet: capacity sent as "40" or 40.0, layouts in any case de-duplicated, operating-hours validation, edit validated like add, unknown fields rejected, unknown venue 404, no history for no-op or rejected edits, role read from the database not the token, every other role refused, login required.

## Before merging

Run `backend/db/venue_catalogue.sql`, then `backend/db/test_role.sql`, in the Supabase SQL editor as the project owner. The CI `supabase-schema` job fails until the table exists.

For AC9 also run `backend/db/venue_setup_turnaround_minutes.sql` (adds the two columns to `venues`; no new table, so `test_role.sql` need not be re-run). Until it is run, `test_database_tables_match_the_models` fails for everyone.

**Deleting venues (CF08, 4 Nov 2026):** Venue Staff delete a venue by archiving it; see [CF08-archive-venue.md](CF08-archive-venue.md). An archived venue can't be edited until it is restored (409 `archived`), and the change history also shows "Archived" and "Restored" entries.
