# SCRUM-88 — Venue becomes unavailable after booking: Test Cases

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
- **A7 — The event (AC4):** an affected event whose status is `confirmed` goes back to `approved`, which is the Planning stage (SCRUM-92 A2). Nothing else about it changes, including the confirmation audit fields. An event in any other status keeps it. The event's planning view shows the flag on the booking and `change_review: {needed: true, reason}` while any of its bookings is flagged.
- **A8 — New bookings (AC5):** a request inside the period is refused up front with `409 reason: "conflict"`, naming the unavailable period and its reason in the message; a request that starts exactly when the period ends is allowed; other venues are unaffected. A pending request that is already waiting cannot be approved inside the period (SCRUM-41 conflict check).
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

Extra cases: bad formats and non-text values; every problem named at once; unknown field; reason over 500 characters; periods listed per venue in time order; 404 before 403; 401 without a session or for a deleted user; a booking that has already ended is not flagged; a booking overlapped by two periods is listed once; a cancelled booking leaves the list; the empty list says so; only Venue Staff can list; the list reports 503; a coordinator with two affected events is told about each; the period is saved even when the email cannot be queued; other event statuses are left alone; the planning view of an unaffected event has no flag; a pending request cannot be approved inside a new period; venue search does not offer the venue inside the period; a failed save of the flags or the notifications saves nothing, and a retry works.

## Before merging

Run `backend/db/venue_unavailable_periods.sql` in the Supabase SQL editor as the project owner, then `backend/db/test_role.sql` again (new table). It is safe to re-run. The CI `supabase-schema` job fails until it has been run.
