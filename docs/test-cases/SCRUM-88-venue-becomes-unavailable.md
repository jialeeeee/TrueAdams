# SCRUM-88 — Venue becomes unavailable after booking: Test Cases

> **Latest execution (5 Nov 2026):** every automated case in this document passes: the full backend suite on a PostgreSQL database built by `backend/ci/build_test_database.py` (1,496 tests, 100% of statements and branches), the full frontend suite with Vitest (100% coverage), and CI. The main journey of every role is also covered end to end by `e2e/test_journeys.py` (CI job `e2e`); browser checks this document names for individual screens remain manual. Execution notes further down record earlier runs and are kept as history; where they say a case was not run, pending or blocked, this line is the current status.

**User story:** As Venue Staff, I want to mark a venue unavailable for a period even when it already has future bookings.

**Created:** 31 Oct 2026 · **Source of the cases:** the "Sprint 4 test cases" tab of the ConnectSphere Backlog to Feature Map sheet (IS212-US88-TC1 to TC29) · **Automated tests:** `backend/tests/test_venue_unavailable.py`, `frontend/src/pages/VenueUnavailablePage.test.jsx`, `frontend/src/pages/ReplacementNeededPage.test.jsx`, `frontend/src/pages/EventPlanningPage.test.jsx` · **Status:** automated cases pass locally; browser walk-through still to be done by hand · **Related:** SCRUM-36/64 (calendar), SCRUM-39/41 (request, conflicts), SCRUM-93 (confirm event), SCRUM-89 (replacement venue)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | Venue Staff can record an unavailable period (reason, start, end) on any venue, whether or not it has confirmed bookings in that period. |
| AC2 | Each overlapping confirmed booking is flagged "Venue unavailable: replacement needed" and listed for Venue Staff. It is not cancelled and the event's information is unchanged. |
| AC3 | The coordinator of each affected event is notified with the event, venue and affected period. |
| AC4 | An affected event that was Confirmed returns to Planning for change review. It is not cancelled and its information is kept. |
| AC5 | The calendar shows the period as unavailable and new bookings inside it are blocked. |
| AC6 | Only Venue Staff can record the period. |

## Working assumptions (to confirm)

- **A1 — What an unavailable period is:** a `VenueBlock` (reason, start, end) — the table SCRUM-36/64 already read, so the calendar, venue search, the request-time check and the approval check already treat it as unavailable. Nothing about blocks changes except that Venue Staff can now record them.
- **A2 — Recording it:** `POST /api/venues/<id>/unavailable` with `reason`, `start_time`, `end_time` (`YYYY-MM-DDTHH:MM`). Reason is required text of at most 500 characters; start and end are required; the end must be **after** the start, so a zero-length period is refused and a one-minute period is allowed (the sheet's open question on TC7). Times in the past are not refused. Every problem is named at once (400 `fields`). Unknown fields are refused. Venue Staff are not linked to venues in this model (SCRUM-69 A1), so any Venue Staff user can record a period on any venue (TC29).
- **A3 — Which bookings are flagged:** the venue's `confirmed` bookings whose occupied period (SCRUM-84: with the venue's setup and turnaround) overlaps the period, half-open, and that have not ended yet. The sheet's open question on TC16 is answered as: pending, tentative, rejected and cancelled bookings are **not** flagged, because the criterion names confirmed bookings only. A booking whose occupied period only touches the period is not flagged. A booking already flagged by an earlier period is flagged once (the list shows the first period that flagged it).
- **A4 — Where the flag lives:** a new table `venue_replacement_flags` (one row per flagged booking: booking, venue, the period that raised it, who and when, status `flagged`), so the booking row itself is never touched. SCRUM-89 later marks a flag `replaced`.
- **A5 — Listing:** Venue Staff list the flagged bookings at `GET /api/venues/replacement-needed`, and a venue's own periods at `GET /api/venues/<id>/unavailable` (Venue Staff only; coordinators see the periods on the availability calendar). A flagged booking that is cancelled afterwards leaves the list.
- **A6 — Notification (AC3):** each affected event's current coordinator gets one in-app notification per recorded period (kind `venue_unavailable`) naming the event, the venue, the unavailable period and the reason, saved in the same commit as the period; the email is queued afterwards and a broker outage does not undo the save. A coordinator with two affected events is told about each. Coordinators of unaffected events get nothing.
- **A7 — The event (AC4):** an affected event whose status is `confirmed` goes back to `approved`, which is the Planning stage (SCRUM-92 A2). Nothing else about it changes, including the confirmation audit fields. An event in any other status keeps it. The event's planning view shows `flag` on the booking and `change_review: {needed: true, reason}` on the event while a booking is flagged; both keys are left out otherwise, as `safety_check` is.
- **A8 — New bookings (AC5):** a request inside the period is refused up front with `409 reason: "conflict"`, naming the unavailable period and its reason in the message; a request that starts exactly when the period ends is allowed; other venues are unaffected. A pending request that is already waiting cannot be approved inside the period (SCRUM-41 conflict check).
- **A10 — Pending requests and holds (added 3 Nov 2026):** they are not flagged (A3), but they can no longer be approved or confirmed inside the period, so each affected event's coordinator is told now rather than when that fails: one in-app notification per event (kind `venue_unavailable_request`) naming the venue, the period, the reason and each request's times and whether it is pending or on hold, saved in the same commit, with the email queued afterwards. Expired holds, rejected and cancelled requests are not mentioned. The response lists them as `requests_warned`. Nothing about the requests changes. *(Q1)*
- **A11 — The safety check starts again (team assumption, added 4 Nov 2026):** the event's safety decision was made on a venue it can no longer use, so recording the period clears the safety decision of every affected event, whether Confirmed or not (`app/events/safety.py`, as SCRUM-70 AC11 does for an accepted change), and the coordinator's notification adds "Its safety check was cleared, so it needs a new safety check once a replacement venue is confirmed." A flagged booking also stops counting towards covering the event: the event leaves the Safety Officer's list (SCRUM-90 AC1) and can't be confirmed (SCRUM-93 AC2, missing "Replacement for an unavailable venue") until other confirmed bookings cover its whole period, for example an approved replacement (SCRUM-89). Without this, an event could be re-confirmed on the unavailable venue with its old safety approval. *(Q2)*
- **A9 — All or nothing:** the period, the flags, the notifications and the event status changes are saved in one transaction. If any part fails, nothing is saved and the reply is 503 (retryable).

## Test cases

| Sheet ID | Automated by | What it checks |
|----------|--------------|----------------|
| TC1 | `test_tc1_venue_staff_record_a_period_on_a_venue_with_no_bookings` | Period saved and listed with reason, start, end |
| TC2 | `test_tc2_a_period_can_be_recorded_over_a_confirmed_booking` | Saved although B-801 overlaps |
| TC3 | `test_tc3_a_reason_is_required` | Blocked, nothing recorded, B-801 not flagged |
| TC4 | `test_tc4_a_start_is_required` | As above |
| TC5 | `test_tc5_an_end_is_required` | As above |
| TC6 | `test_tc6_an_end_before_the_start_is_rejected` | "end must be after the start" |
| TC7 | `test_tc7_an_end_equal_to_the_start_is_rejected` | Zero length refused |
| TC8 | `test_tc8_a_period_one_minute_long_is_accepted` | One minute allowed |
| TC9 | `test_tc9_a_confirmed_booking_that_overlaps_is_flagged_and_listed` | Flag text, event, venue, times, period in the list |
| TC10 | `test_tc10_the_flagged_booking_is_not_cancelled_and_the_event_is_unchanged` | Booking and event unchanged |
| TC11 | `test_tc11_a_booking_that_starts_before_the_period_and_ends_inside_it_is_flagged` | B-802 and B-801 flagged |
| TC12 | `test_tc12_a_booking_that_ends_exactly_when_the_period_starts_is_not_flagged` | Touching: not flagged |
| TC13 | `test_tc13_a_booking_that_ends_one_minute_after_the_period_starts_is_flagged` | One minute of overlap: flagged |
| TC14 | `test_tc14_a_booking_at_another_venue_at_the_same_time_is_not_flagged` | Other venue |
| TC15 | `test_tc15_a_booking_on_a_different_day_is_not_flagged` | Other day |
| TC16 | `test_tc16_a_booking_that_is_not_confirmed_is_not_flagged` | Pending, tentative, rejected, cancelled |
| TC17 | `test_tc17_the_coordinator_is_notified_with_the_event_venue_and_period` | Notification text |
| TC18 | `test_tc18_each_coordinator_is_notified_about_their_own_event_only` | Alice and Ben |
| TC19 | `test_tc19_the_coordinator_of_an_unaffected_event_is_not_notified` | Unaffected |
| TC20 | `test_tc20_a_confirmed_event_returns_to_planning_and_is_not_cancelled` (+ planning view) | approved, same details, change review shown |
| TC21 | `test_tc21_an_affected_event_that_was_not_confirmed_keeps_its_status` | Approved event stays approved, booking flagged |
| TC22 | `test_tc22_the_calendar_shows_the_period_as_unavailable` | 08:59 and 18:00 free, 09:00–17:59 unavailable |
| TC23 | `test_tc23_a_new_request_inside_the_period_is_blocked` | 409, message says unavailable, nothing created |
| TC24 | `test_tc24_a_request_that_starts_one_minute_before_the_period_ends_is_blocked` | One minute inside |
| TC25 | `test_tc25_a_request_that_starts_exactly_when_the_period_ends_is_allowed` | Half-open |
| TC26 | `test_tc26_the_same_time_at_another_venue_is_not_blocked` | Other venue |
| TC27 | `test_tc27_an_event_coordinator_cannot_record_a_period`; frontend | 403, nothing changes, no action shown |
| TC28 | `test_tc28_an_attendee_cannot_record_a_period` | 403 |
| TC29 | `test_tc29_a_second_venue_staff_user_can_record_a_period` | The role, not one user |
| TC-88-A11-01 | `test_tc_88_a11_01_a_confirmed_event_loses_its_safety_approval` | Approved, safety decision empty, confirmation record kept, coordinator told |
| TC-88-A11-02 | `test_tc_88_a11_02_an_approved_event_loses_a_negative_decision_too` | Changes requested is cleared too |
| TC-88-A11-03 | `test_tc_88_a11_03_an_event_with_no_safety_decision_is_not_told_about_one` | No safety sentence |
| TC-88-A11-04 | `test_tc_88_a11_04_an_event_at_another_venue_keeps_its_safety_approval` | Unaffected event unchanged |
| TC-88-A11-05 | `test_tc_88_a11_05_a_flagged_booking_takes_the_event_off_the_safety_list` | Off the SCRUM-90 list |
| TC-88-A11-06 | `test_tc_88_a11_06_another_confirmed_booking_puts_it_back_on_the_list` | Back once covered |
| TC-88-A11-07 | `test_tc_88_a11_07_confirming_asks_for_a_replacement_venue` | 409, missing "Replacement for an unavailable venue" |
| TC-88-A11-08 | `test_tc_88_a11_08_with_a_replacement_and_a_new_safety_check_it_can_be_confirmed` | Confirmed again |
| TC-88-A11-09 | `test_tc_88_a11_09_a_gap_not_caused_by_a_flag_still_asks_for_a_booking` | "Confirmed venue booking" as before |
| TC-88-A11-10 | `test_tc_88_a11_10_an_event_without_times_still_asks_for_a_booking` | As before |

Extra cases: bad formats and non-text values; every problem named at once; unknown field; reason over 500 characters; periods listed per venue in time order; 404 before 403; 401 without a session or for a deleted user; a booking that has already ended is not flagged; a booking overlapped by two periods is listed once; a cancelled booking leaves the list; the empty list says so; only Venue Staff can list; the list reports 503; a coordinator with two affected events is told about each; the period is saved even when the email cannot be queued; other event statuses are left alone; the planning view of an unaffected event has no flag; a pending request cannot be approved inside a new period; venue search does not offer the venue inside the period; a failed save of the flags or the notifications saves nothing, and a retry works.

## Open questions for the customer

| ID | Question | Affects |
|---|---|---|
| Q1 | Should a coordinator with a pending venue request or a tentative hold inside a new unavailable period be told when the period is recorded? **Assumed yes (A10)**: they are warned, but the request is neither flagged nor changed. | A10; `RequestWarningTests` |
| Q2 | When a venue becomes unavailable, must the event pass a new safety check on its replacement venue? **Assumed yes (A11, team assumption)**: its safety decision is cleared and the flagged booking no longer counts towards confirmation. | A11; `test_venue_unavailable_safety.py` |

## Before merging

Run `backend/db/venue_unavailable_periods.sql` in the Supabase SQL editor as the project owner, then `backend/db/test_role.sql` again (new table). It is safe to re-run. The CI `supabase-schema` job fails until it has been run.
