# SCRUM-38 — Assess a Venue Against Event Requirements: Test Cases

> **Latest execution (5 Nov 2026):** every automated case in this document passes: the full backend suite on a PostgreSQL database built by `backend/ci/build_test_database.py` (1,496 tests, 100% of statements and branches), the full frontend suite with Vitest (100% coverage), and CI. The main journey of every role is also covered end to end by `e2e/test_journeys.py` (CI job `e2e`); browser checks this document names for individual screens remain manual. Execution notes further down record earlier runs and are kept as history; where they say a case was not run, pending or blocked, this line is the current status.

**User story:** As an Event Coordinator, I want to check a venue against an event's requirements, so that I can tell whether it is suitable before requesting it.

**Created:** 20 Oct 2026 · **Source of the cases:** the "Sprint 3 test cases" tab of the ConnectSphere Backlog to Feature Map sheet (IS212-US38-TC1 to TC14) · **Automated tests:** `backend/tests/test_venue_suitability.py`, `frontend/src/pages/VenueSuitabilityPage.test.jsx` (+ the link in `EventPlanningPage.test.jsx`) · **Status:** automated cases pass locally (20 Oct 2026); browser walk-through still to be done by hand · **Related:** SCRUM-63 (defined facility/accessibility/layout lists), SCRUM-53 (planning edits)

**Changed 4 Nov 2026 (CF11, G4 clarification #8):** "accessibility/layout mismatches count and should be reflected by the co-ordinator on suitability". The check already counted them, but nothing in the app could record what an event needs, so for any event made through the app the facility and accessibility lines were always Unable to assess. The coordinator now records them on the event's planning page (A2, TC15 to TC20).

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The coordinator can run a suitability check for a selected event and venue using their saved information. |
| AC2 | Expected attendance above the venue's recorded capacity is identified as a mismatch. |
| AC3 | A required facility, accessibility feature, or room layout that the venue does not support is identified as a mismatch. |
| AC4 | The coordinator can see which checked requirements match and which do not. |
| AC5 | If information needed for a check is missing, that requirement is shown as Unable to assess, not assumed to be satisfied. |
| AC6 | If all applicable checks pass, the venue is shown as meeting the checked requirements; the result does not claim that a booking has been confirmed. |

## Working assumptions (to confirm)

- **A1 — Endpoint:** `GET /api/events/<id>/venue-suitability?venue_id=<n>`, read-only, for the event's current coordinator only (401, 404, 403, 400, 503). It never books, requests or changes anything.
- **A2 — What an event needs:** three new nullable Event columns (`db/event_requirements.sql`): `required_facilities`, `required_accessibility_features`, `required_layouts`, each a list of names. NULL means not recorded (shown as Unable to assess); an empty list means it needs none (shown as Not required). They are saved through `PATCH /api/events/<id>` as **normal** planning fields (they change no existing arrangement); this adds to the SCRUM-53 field list.
  - **Answered 4 Nov 2026 (CF11):** the coordinator records them in an **Event requirements** section of the event's planning page: tick boxes for the facilities, accessibility features and layouts Venue Staff choose from (SCRUM-63's defined lists), and a **None needed** box per group. Nothing ticked saves "not recorded" (NULL); None needed saves an empty list; names are saved in the boxes' order. A name already saved outside the defined lists keeps its own box, so saving never drops it. The planning view (`GET /api/events/<id>/planning`) and the PATCH reply carry them as `requirements: {facilities, accessibility_features, layouts}`. A cancelled event shows them without boxes (SCRUM-53 AC3). Organisers also choose layouts on the request once CF02 (SCRUM-28) is merged.
  - **Team decision, kept from this story:** they stay **normal** edits even once a venue is booked. Saving them changes no booking, reservation or registration, only what the next check compares against (CF07: no confirmed commitment changes silently). The coordinator then decides on any booking that no longer matches. If the team prefers, the stricter alternative is to make them restricted once the event has a live venue booking (SCRUM-52).
- **A3 — Checks:** one line for attendance, then one line per required facility, accessibility feature and layout (or one "Not required"/"Unable to assess" line for a category). Names match ignoring case and extra spaces.
  - Attendance: expected above capacity is a mismatch; equal or below matches; either missing is Unable to assess.
  - A venue list that is NULL is Unable to assess; a recorded list without the item is a mismatch.
- **A4 — Empty layout list at the venue:** the sheet's TC11 asks whether an empty layout list means "not recorded". Following AGENTS.md (NULL is not recorded; an empty list is a recorded absence) it is treated as **none supported (mismatch)**. **Open question for the customer.**
- **A5 — Overall result:** any mismatch gives "does not meet all the checked requirements"; otherwise anything Unable to assess gives "could not be fully assessed" (never "meets"); otherwise "meets the checked requirements". The wording never says booked, confirmed, approved or reserved.
- **A6 — Names are not checked against SCRUM-63's defined lists** here, so this story does not depend on that branch. Once both are merged, the requirement lists can be validated against the same lists.
- **A7 — Capacity only:** the check does not look at dates or availability (that is the calendar, search and conflict checks).

## Test cases

| Sheet ID | Automated by | What it checks |
|----------|--------------|----------------|
| TC1 | `test_tc1_one_line_each_for_attendance_facility_accessibility_and_layout`; frontend | One line each, from the saved details |
| TC2 | `test_tc2_a_venue_must_be_chosen`; frontend | No venue: 400/404, no check run, message shown |
| TC3 | `test_tc3_uses_the_latest_saved_event_information` (+ venue) | Changed attendance changes the result |
| TC4 | `test_tc4_one_above_the_capacity_is_a_mismatch` | 121 against 120 |
| TC5 | `test_tc5_equal_to_the_capacity_is_a_match` | 120 against 120 |
| TC6 | `test_tc6_a_facility_the_venue_lacks_is_a_mismatch` | Video conferencing |
| TC7 | `test_tc7_an_accessibility_feature_the_venue_lacks_is_a_mismatch` | Hearing loop |
| TC8 | `test_tc8_a_layout_the_venue_does_not_support_is_a_mismatch` | Banquet |
| TC9 | `test_tc9_matches_and_mismatches_are_listed_separately_and_labelled`; frontend | Labelled lines, mixed result |
| TC10 | `test_tc10_missing_attendance_is_unable_to_assess`; frontend | Attendance not recorded |
| TC11 | `test_tc11_layouts_not_recorded_at_the_venue_is_unable_to_assess` | Layouts NULL |
| TC12 | `test_tc12_an_unassessed_requirement_stops_the_venue_meeting_the_requirements`; frontend | Overall is not "meets" |
| TC13 | `test_tc13_passing_every_check_meets_the_checked_requirements`; frontend | Every line a match, overall "meets" |
| TC14 | `test_tc14_a_passing_result_does_not_claim_or_create_a_booking`; frontend | No booking words, no booking, status unchanged |
| TC15 (CF11) | `PlanningRequirementsTests.test_the_planning_view_shows_what_the_event_needs` | The planning view returns each list: null (not recorded), [] (none needed), names |
| TC16 (CF11) | `PlanningRequirementsTests.test_recorded_requirements_show_mismatches_on_the_next_check` | Before: Unable to assess. After the coordinator saves Microphone, Wheelchair ramp and Theatre, Marina Room shows accessibility and layout **mismatches** and "does not meet" (clarification #8) |
| TC17 (CF11) | frontend "shows what the event needs, telling not recorded from none needed" | Saved: Not recorded / None needed / names; boxes ticked to match; an extra saved name keeps its box |
| TC18 (CF11) | frontend "saves the ticked requirements and shows them as saved" | PATCH sends names in list order, null for nothing ticked; boxes disabled while saving; "Changes saved." and the saved lines update |
| TC19 (CF11) | frontend "clears the names when None needed is ticked, and None needed when a name is" | None needed and names exclude each other; unticking both sends null |
| TC20 (CF11) | frontend "explains … and keeps the ticks for a retry", "shows a cancelled event's requirements without letting them be changed", "ignores a save that finishes after another event was opened" | Server message with field problems, fallback without one or with no network, ticks kept, retry succeeds; cancelled: no boxes; a late reply after opening another event changes nothing |

Extra cases: matching ignores case/spacing; below capacity matches; venue capacity/facilities/accessibility not recorded; event requirements not recorded; "Not required" categories; a mismatch outweighs an unassessed line; login, unknown event, other coordinators/roles refused; a database failure is a retryable error with no result; requirement lists can be saved, cleared and validated through PATCH.

**CF11 evidence (4 Nov 2026, local PostgreSQL built from the models):** backend 1,369 tests pass with 100% coverage; frontend 664 tests pass with 100% statements, branches, functions and lines. Breaking each new rule in turn (the two lists in the planning view; names in list order; nothing ticked saving null; None needed excluding names; extra saved names kept; Not recorded vs None needed; a late reply after opening another event; field problems shown; a cancelled event read-only; boxes locked while saving; saved lines refreshed) is caught by a test in 12 of 12 cases.

## Before merging

Run `backend/db/event_requirements.sql` in the Supabase SQL editor as the project owner (adds three nullable columns to `events`; safe to re-run). The CI `supabase-schema` job fails until it has been run. The three requirement fields are listed in the SCRUM-53 test-case doc's normal fields (R1, added 4 Nov 2026).
