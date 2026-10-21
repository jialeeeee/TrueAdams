# SCRUM-63 — Maintain the Venue Catalogue: Test Cases

**User story:** As Venue Staff, I want to add and edit venues in the catalogue, so that coordinators always see accurate venue information.

**Created:** 20 Oct 2026 · **Source of the cases:** the "Sprint 3 test cases" tab of the ConnectSphere Backlog to Feature Map sheet (IS212-US63-TC1 to TC16) · **Automated tests:** `backend/tests/test_venue_catalogue.py`, `frontend/src/pages/VenueFormPage.test.jsx` · **Status:** all automated cases pass locally (20 Oct 2026); TC13's "stop the database" variant and the browser walk-through are still to be run by hand.

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

## Working assumptions (to confirm)

- **A1 — Endpoints:** `POST /api/venues/` adds, `PUT /api/venues/<id>` edits (only the fields sent change), `GET /api/venues/options` gives the defined lists, `GET /api/venues/<id>/history` gives the change history. All are Venue Staff only (role read from the database, 403 otherwise).
- **A2 — Order of checks:** 401, 403, 404, 400 (every invalid field at once, in `fields`), then a database failure is 503 `retryable`. Nothing is saved on any failure.
- **A3 — The defined lists are those in the test cases:** facilities Projector, Microphone, Video conferencing; accessibility features Wheelchair ramp, Hearing loop; layouts Theatre, Classroom, Boardroom, Banquet. Layouts are stored in the lower-case keys venue search already uses. **Open question:** the customer has not given the full lists; existing seed venues use other values (e.g. Stage, Wi-Fi), which stay as they are but can't be chosen for new venues.
- **A4 — Operating hours** are optional. When given they must be in the form the availability calendar understands (e.g. `Mon-Fri 08:00-22:00`); empty means "not recorded".
- **A5 — Change history:** one `venue_changes` row per add or edit, in the same commit as the change, with a from/to for each field touched. An edit that changes nothing records nothing.
- **A6 — Add/Edit buttons** are shown only when `GET /venues/options` succeeds, so the screen never decides roles itself.
- **A7 — Out of scope:** deleting or disabling a venue; contact details, description, area, parking and catering (not in AC1).

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

Extra cases beyond the sheet: capacity sent as "40" or 40.0, layouts in any case de-duplicated, operating-hours validation, edit validated like add, unknown fields rejected, unknown venue 404, no history for no-op or rejected edits, role read from the database not the token, every other role refused, login required.

## Before merging

Run `backend/db/venue_catalogue.sql`, then `backend/db/test_role.sql`, in the Supabase SQL editor as the project owner. The CI `supabase-schema` job fails until the table exists.
