# SCRUM-98 — Coordinator cancels an event: Test Cases

> **Latest execution (5 Nov 2026):** every automated case in this document passes: the full backend suite on a PostgreSQL database built by `backend/ci/build_test_database.py` (1,496 tests, 100% of statements and branches), the full frontend suite with Vitest (100% coverage), and CI. Execution notes further down record earlier runs and are kept as history; where they say a case was not run, pending or blocked, this line is the current status.

**User story:** As an Event Coordinator, I want to cancel an event at its organiser's request so that its venues, equipment and attendee places are released and everyone affected is told.

**Created:** 4 Nov 2026 · **Status of all cases:** automated cases pass (4 Nov 2026, local PostgreSQL as in CI + Vitest) · **Automated tests:** `backend/tests/test_cancel_event.py`, `frontend/src/pages/EventPlanningPage.cancel.test.jsx` · **Endpoint:** `POST /api/events/<id>/cancel` · **Related:** SCRUM-94 (cancelling one venue booking, and its notice to Venue Staff), SCRUM-44 A10 (equipment is released when an event is cancelled), SCRUM-68 (registration statuses), SCRUM-53 (a cancelled event can't be edited), CF06

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | Only the event's assigned coordinator can cancel it, and only before the event starts. Anyone else is denied and nothing changes. |
| AC2 | A draft, rejected or already cancelled event cannot be cancelled, and the coordinator is told why. |
| AC3 | The coordinator must give a reason (not blank, at most 500 characters), and a confirmation step is shown. Backing out leaves the event unchanged. |
| AC4 | On confirming, the event's status becomes Cancelled, and who cancelled it, when and why are recorded. |
| AC5 | The event's pending, tentative and confirmed venue bookings become Cancelled, and its equipment reservations are released. Their records are kept, and the venues and quantities become available again. |
| AC6 | The event's active registrations are cancelled. |
| AC7 | The organiser, registered attendees, Venue Staff for its venues and Technical Support Staff are notified. |
| AC8 | A cancelled event cannot be edited or reinstated; a similar event needs a new request. |
| AC9 | If saving fails, nothing changes and an error is shown. |

## Working assumptions (to confirm)

- **A1 — Who and when (AC1):** the event's current coordinator (`is_current_coordinator`). The coordinator acts at the organiser's request (team decision, CF06); the system doesn't record the request itself. "Before the event starts" means its start time is after now (Singapore time); an event with no start recorded can be cancelled.
- **A2 — Which events (AC2):** `submitted`, `under_review`, `approved` and `confirmed`. `draft`, `rejected` and `cancelled` are refused with 409 `not_cancellable` naming the status; for a cancelled event the message adds that it can't be reinstated (AC8). A draft is the organiser's own and has no coordinator to cancel it.
- **A3 — The reason (AC3):** required, with a visible character (as SCRUM-60 A3), at most 500 characters after trimming, saved trimmed. The confirmation step is the planning page's form; nothing is sent until the coordinator confirms, and "Back" discards the reason.
- **A4 — What is recorded (AC4):** `events.status = cancelled`, `cancelled_by_id`, `cancelled_at` (naive UTC) and `cancellation_reason` (`db/event_cancellation.sql`). The planning view shows `cancellation: {cancelled_by, cancelled_at, reason}` once cancelled.
- **A5 — What is released (AC5, AC6):** every booking whose status is `pending`, `tentative` or `confirmed` becomes `cancelled`, keeping its row (as SCRUM-94); rejected, already cancelled, expired and replaced bookings are left alone. Reserved equipment is released by SCRUM-44's rule with the reason "The event was cancelled.". `registered` registrations become `cancelled` (SCRUM-68's status for a registration the event cancelled); withdrawn ones are left alone. Pending change requests and reassignment requests stay as they are (SCRUM-70 A1, Q5). The event's venue is kept as a record.
- **A6 — Who is told (AC7):** one in-app notification each (kind `event_cancelled`), saved in the same commit, then an email:
  - the organiser, with who cancelled it, when and the reason;
  - each attendee whose registration was cancelled, without the reason, which is internal planning information (attendee-facing information is kept apart from planning details);
  - every Venue Staff member (they aren't linked to venues, SCRUM-94 A4), listing the venues and times freed, only if a booking was cancelled;
  - every Technical Support Staff member, only if the event had equipment requirements or reservations.
  An email that can't be queued doesn't undo the cancellation; the reply says `email_queued: false`.
- **A7 — All or nothing (AC9):** the event, bookings, registrations, equipment release and notifications are saved in one commit; any failure is 503 `retryable` and nothing changes. Checks, first failure wins: 401 → 404 → 403 → 400 → 409 (`not_cancellable`, then `started`) → 503.

## Seed data (CE-SEED)

Users: organiser **dana**; coordinators **alice** and **ben**; Venue Staff **gus** and **vera**; Technical Support **hana**; Lead **lena**; Safety Officer **sam**; **admin**; attendees **farah**, **gail**, **hugo**, **ivy**. Venues **Hall A** and **Annex**. "Now" is 2027-05-01 09:00.

| Key | What | Details |
|-----|------|---------|
| E1 | Event | "Harbour Talk", approved, organiser dana, coordinator alice, 2027-06-10 10:00–12:00 |
| OTHER | Event | "Other Event", approved, coordinator ben |
| B1 | Booking | Hall A, confirmed, E1's times |
| B2 | Booking | Annex, tentative (hold expires 2027-06-01 12:00) |
| B3 | Booking | Annex, pending |
| B4 / B5 | Bookings | Hall A rejected; Annex cancelled |
| — | Booking | OTHER's confirmed Hall A booking |
| R1 | Equipment | 2 microphones reserved for E1 |
| — | Registrations | farah and gail registered for E1; hugo withdrawn; ivy registered for OTHER |

## Test cases

| ID | Traces to | What it checks | Automated |
|----|-----------|----------------|-----------|
| TC-98-01 | AC1 | 401 (no token, deleted user), 404, 403 for ben, dana, gus, hana, lena, sam, admin and farah without the event's name; 403 before the body; nothing changes | `test_tc_98_01_who_may_cancel_and_in_what_order` |
| TC-98-02 | AC1 | At and after the start: 409 `started`, nothing changes; a minute before: cancelled | `test_tc_98_02_an_event_that_has_started_cannot_be_cancelled`, `test_tc_98_02_one_minute_before_the_start_it_can_be` |
| TC-98-03 | AC2, AC8 | Draft, rejected, cancelled: 409 `not_cancellable` naming the status (cancelled adds "can't be reinstated"); submitted, under review, approved, confirmed: cancelled | `test_tc_98_03_drafts_rejected_and_cancelled_events_cannot_be_cancelled`, `test_tc_98_03_submitted_reviewed_approved_and_confirmed_events_can_be` |
| TC-98-04 | AC3 | Missing, null, empty, spaces, invisible spaces: 400 "Give a reason for cancelling the event."; non-text, not an object, 501 characters: 400; 500 characters (trimmed): saved | `test_tc_98_04_a_reason_is_required`, `test_tc_98_04_the_reason_must_be_text_of_at_most_500_characters` |
| TC-98-05 | AC4 | Cancelled with alice, the time and the trimmed reason; the reply and planning view show them; an event not cancelled has no `cancellation` | `test_tc_98_05_who_when_and_why_are_recorded_and_shown`, `test_tc_98_05_an_event_not_cancelled_shows_no_cancellation` |
| TC-98-06 | AC5 | B1–B3 cancelled, B4, B5 and OTHER's booking unchanged, rows kept; R1 released "The event was cancelled."; counts in the reply; Hall A can be requested again for those times | `test_tc_98_06_live_bookings_are_cancelled_and_equipment_released`, `test_tc_98_06_the_venue_is_free_again` |
| TC-98-07 | AC6 | farah and gail cancelled; hugo withdrawn; ivy registered | `test_tc_98_07_active_registrations_are_cancelled` |
| TC-98-08 | AC7 | dana told with the reason; farah and gail told without it; gus and vera told the venues; hana told; nobody else; one email each; an event with nothing to release tells no staff; requirements without reservations still tell hana; a queue outage keeps the cancellation | `test_tc_98_08_*` (4 tests) |
| TC-98-09 | AC8 | After cancelling: editing 409, cancelling again 409 "can't be reinstated", confirming 409 | `test_tc_98_09_a_cancelled_event_cannot_be_edited_reinstated_or_confirmed` |
| TC-98-10 | AC9 | A failed save of the event, a booking, a registration, the equipment release or a notification: 503 `retryable`, nothing changes | `test_tc_98_10_a_failed_save_changes_nothing` |
| TC-98-11 | AC2 | The planning page offers "Cancel event" for submitted, under review, approved and confirmed events only | frontend "offers cancelling only for events that can be cancelled" |
| TC-98-12 | AC3, AC4 | The confirmation step needs a reason (shown with a count), refuses over 500, "Back" changes nothing; confirming shows the outcome and the cancellation record | frontend "asks for a reason, then cancels and shows the record", "backing out changes nothing", "refuses a reason over 500 characters", "shows the cancellation of an event loaded as cancelled, even without who" |
| TC-98-13 | AC1, AC9 | A refusal or failure is explained and the reason is kept for another try | frontend "explains a refusal or failure and keeps the reason" |

## Traceability matrix

| AC | Test cases |
|----|------------|
| AC1 | 01, 02, 13 |
| AC2 | 03, 11 |
| AC3 | 04, 12 |
| AC4 | 05, 12 |
| AC5 | 06 |
| AC6 | 07 |
| AC7 | 08 |
| AC8 | 03, 09 |
| AC9 | 08, 10, 13 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Should the organiser be able to ask for a cancellation in the system, rather than outside it (as built: the coordinator cancels on their behalf)? | A1 |
| Q2 | Should registered attendees be told the reason (as built: no, it may be internal)? | A6 |
| Q3 | Should a pending change request on a cancelled event be closed automatically (as built: it stays pending and can't be decided)? | A5 |

## Before merging

Run `backend/db/event_cancellation.sql` in the Supabase SQL editor as the project owner. It adds columns only, so `db/test_role.sql` doesn't need to be run again. It is safe to re-run. The CI `supabase-schema` job fails until it has been run.
