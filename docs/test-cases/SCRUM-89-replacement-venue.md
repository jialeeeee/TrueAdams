# SCRUM-89 — Coordinator replaces an unavailable venue: Test Cases

> **Latest execution (5 Nov 2026):** every automated case in this document passes: the full backend suite on a PostgreSQL database built by `backend/ci/build_test_database.py` (1,496 tests, 100% of statements and branches), the full frontend suite with Vitest (100% coverage), and CI. The main journey of every role is also covered end to end by `e2e/test_journeys.py` (CI job `e2e`); browser checks this document names for individual screens remain manual. Execution notes further down record earlier runs and are kept as history; where they say a case was not run, pending or blocked, this line is the current status.

**User story:** As an Event Coordinator, I want to request a replacement venue for a booking that was flagged because the venue became unavailable, so that my event keeps a venue.

**Created:** 31 Oct 2026 · **Source of the cases:** the "Sprint 4 test cases" tab of the ConnectSphere Backlog to Feature Map sheet (IS212-US89-TC1 to TC17) · **Automated tests:** `backend/tests/test_venue_replacement.py`, `frontend/src/pages/ReplacementVenuePage.test.jsx`, `frontend/src/pages/VenueBookingRequestPage.test.jsx` · **Status:** automated cases pass locally; browser walk-through still to be done by hand · **Depends on:** SCRUM-88 (the flag), SCRUM-84 (occupied periods) · **Related:** SCRUM-38 (suitability), SCRUM-39/40/69 (request, approve, reject), SCRUM-85 (several venues per event)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | From a flagged booking, the coordinator can search for another venue for the same event and submit a booking request. The request is linked to the flagged booking. |
| AC2 | The search and the request use the same suitability, availability and conflict checks, and the same Venue Staff approval, as any new booking. The event's other venue bookings are unchanged. |
| AC3 | When Venue Staff approve the replacement, the flagged booking is marked Replaced and its original record is kept. |
| AC4 | If Venue Staff reject the replacement, the flagged booking stays flagged and the coordinator is notified. |
| AC5 | Only the event's coordinator can request a replacement. Anyone else is denied and nothing changes. |
| AC6 | If saving fails, no request is created and the flagged booking is unchanged. |

## Working assumptions (to confirm)

- **A1 — What a replacement request is:** an ordinary pending venue request (SCRUM-39) for the same event, **at the flagged booking's date and time and with its venue requirements**, linked to the flagged booking by the new column `venue_bookings.replaces_booking_id`. The coordinator chooses only the venue, so the request takes no times, event or other fields (400 if sent). The sheet's open question on TC2 is answered as: the search is pre-filled from the flagged booking and the date and time cannot be edited.
- **A2 — Endpoints:** `GET /api/venues/bookings/<id>/replacement` gives the flagged booking and its event (the search screen's header); `POST` on the same path with `{"venue_id"}` creates the request. The search itself reuses what a new booking uses: the venue list, `GET /api/venues/search` for availability, and `GET /api/events/<id>/venue-suitability` for suitability. Only the event's current coordinator may use either (403 for everyone else, as in SCRUM-94 A1).
- **A3 — Check order:** 401, 404 (booking, then venue), 403, 400 (venue missing or not a whole number; unknown fields), then 409.
- **A4 — When it is allowed (409 otherwise):** the booking is flagged (`venue_replacement_flags.status = flagged`) and still confirmed (`reason: "not_flagged"`); the event is still approved, i.e. in Planning (`event_not_approved`, as SCRUM-39 A2); the flagged booking has no replacement request still waiting — pending, or on an unexpired tentative hold (`already_requested`; once one is rejected, or its hold expires, another can be asked for); the event has no pending request for the new venue at an overlapping time already (`already_requested`, naming it); and the new venue passes the same conflict check as a new request — confirmed bookings, blocks (which include the unavailable period that flagged the booking), unexpired holds and the venues' setup and turnaround (SCRUM-84), so the venue that became unavailable cannot be chosen (`conflict`, message names the unavailable period).
- **A5 — What it does not check:** suitability is shown on the search screen but does not block a request, exactly as for a new booking (SCRUM-38). The flagged booking itself is not a conflict, so a replacement for the same time at another venue is allowed. The event's other bookings are never read or changed.
- **A6 — Approval (AC3):** Venue Staff approve it with the existing approve action. In the same commit, if the flagged booking is still confirmed and flagged, its status becomes `replaced` and its flag's status becomes `replaced`. Nothing else about the flagged booking changes (venue, event, times, requirements and the flag row are kept), and the event's venue moves to the new venue if it was the old one. A replaced booking blocks nothing and leaves the "replacement needed" lists. **Venue Staff may instead place the replacement on a tentative hold (SCRUM-87); when the coordinator confirms that hold (SCRUM-86), the same happens in the same commit** (review fix, 3 Nov 2026: confirming used to leave the flagged booking confirmed beside it). If the flagged booking was cancelled in the meantime, the approval or confirmation goes ahead and replaces nothing. An approval or confirmation the database's no-overlap rule refuses is a 409 conflict, as for any approval (SCRUM-41 A4), and replaces nothing.
- **A7 — Rejection (AC4):** the existing reject action. The flagged booking and its flag are untouched, so it stays flagged, and the coordinator's existing rejection notification also says the original booking is still flagged "Venue unavailable: replacement needed".
- **A8 — What the coordinator sees:** the event's venue requests (`GET /api/venues/bookings?event_id=`) give a flagged or replaced booking an `unavailable_flag` (`text`, `status`, `replaced_by`), and a replacement request carries `replaces`. A booking with neither looks as before.
- **A9 — Failure (AC6):** the request is one insert. If saving fails the reply is 503 (retryable) and nothing exists. A failed approval leaves the flagged booking confirmed and flagged.

## Test cases

| Sheet ID | Automated by | What it checks |
|----------|--------------|----------------|
| TC1 | `test_tc1_the_coordinator_requests_a_replacement_and_it_is_linked`; frontend | Pending request at V-103, same event/times, linked to B-901 |
| TC2 | `test_tc2_the_search_is_for_the_same_event`; frontend | Event, times, attendance shown; not editable |
| TC3 | `test_tc3_a_booking_that_is_not_flagged_cannot_be_replaced`; frontend | 409 not_flagged; no action on B-902 |
| TC4 | `test_tc4_a_venue_must_be_chosen`; frontend | 400 venue_id; message asks to select a venue |
| TC5 | `test_tc5_a_venue_with_a_conflicting_booking_is_blocked`; frontend | V-104 booked: 409 conflict |
| TC6 | `test_tc6_the_search_shows_when_a_venue_does_not_suit_the_event`; frontend | V-102: attendance mismatch (80 vs 50) |
| TC7 | `test_tc7_the_unavailable_venue_cannot_be_the_replacement` | V-101: 409, "unavailable" |
| TC8 | `test_tc8_a_venue_is_blocked_when_only_setup_or_turnaround_conflicts` | Setup 09:30 overlaps B-903's turnaround |
| TC9 | `test_tc9_the_request_goes_to_venue_staff_like_any_new_booking` | Listed as Pending with `replaces` |
| TC10 | `test_tc10_the_events_other_venue_bookings_are_unchanged` | B-902 untouched |
| TC11 | `test_tc11_approving_the_replacement_marks_the_flagged_booking_replaced` (+ original record kept) | B-901 Replaced; venue, times, flag kept |
| TC12 | `test_tc12_the_flagged_booking_stays_flagged_while_the_replacement_waits` | Still confirmed and flagged |
| TC13 | `test_tc13_rejecting_the_replacement_keeps_the_booking_flagged_and_tells_the_coordinator` | Still flagged; notification |
| TC14 | `test_tc14_another_coordinator_cannot_request_a_replacement`; frontend | 403, nothing changes, no action |
| TC15 | `test_tc15_venue_staff_cannot_request_a_replacement` | 403 |
| TC16 | `test_tc16_an_attendee_cannot_request_a_replacement` | 403 |
| TC17 | `test_tc17_a_failed_save_creates_no_request_and_leaves_the_booking_unchanged`; frontend | 503; nothing created |

Extra cases: the request takes no times, event or other fields; unknown booking or venue (404); no session (401); a body that is not JSON; only one replacement waiting per flagged booking, and another after a rejection; an event no longer approved; a cancelled flagged booking; approving moves the event's venue; a replaced booking leaves the lists and cannot be replaced again; the event's other bookings are untouched by the decision; other roles (403); a reassigned event's new coordinator only; 403 comes before the flag check; a failed approval leaves the booking flagged; a retry after a failure succeeds; a pending request for the same venue and time is not repeated; approving after the flagged booking was cancelled replaces nothing; an approval refused by the database rule is a conflict, not a failure. Held replacements (`HeldReplacementTests`): confirming the hold marks the flagged booking Replaced and moves the event's venue; a held replacement still counts as waiting; once its hold has expired another can be asked for; a confirmation refused by the database rule replaces nothing.

## Before merging

Run `backend/db/venue_replacement_requests.sql` in the Supabase SQL editor as the project owner (after SCRUM-88's `venue_unavailable_periods.sql`). It adds `venue_bookings.replaces_booking_id`; no new table, so `test_role.sql` need not be re-run. It is safe to re-run. The CI `supabase-schema` job fails until it has been run.
