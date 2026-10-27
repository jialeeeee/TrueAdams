# SCRUM-94 — Coordinator Cancels a Venue Booking: Test Cases

**User story:** As an Event Coordinator, I want to cancel a venue booking for my event, so that the venue is released when I no longer need it.

**Created:** 26 Oct 2026 · **Branch:** `feature/SCRUM-94-coordinator-cancels-a-venue-booking` · **Status of all cases:** Automated cases pass (26 Oct 2026, Supabase test database + Vitest). They failed first (red: no endpoint, no booking list). Breaking the coordinator check, the cancellable statuses, the status change, the staff notifications or the release of the event's venue makes them fail again. Frontend cases 07–09 and 21 also to be checked manually in the browser · **Automated tests:** `backend/tests/test_venue_booking_cancellation.py`, `frontend/src/pages/VenueBookingRequestPage.test.jsx` · **Builds on:** SCRUM-39 (venue requests and the coordinator's venue request page), SCRUM-40 (approval sets the event's venue), SCRUM-41 (conflict checks), SCRUM-69 (the event's saved requests), SCRUM-87 (tentative holds)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | Only the event's coordinator can cancel a booking, and only one that is Pending, Tentative or Confirmed. Anyone else is denied and nothing changes. |
| AC2 | A confirmation step is shown. Backing out leaves the booking unchanged. |
| AC3 | On confirming, the booking status becomes Cancelled, its record is kept and the venue slot is free again. |
| AC4 | Venue Staff for that venue are notified. |
| AC5 | The event's other venue bookings are unchanged. |
| AC6 | If saving fails, the booking is unchanged and an error is shown. |

## Working assumptions

Our current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before changing the code.

- **A1 — Who may cancel:** the event's current coordinator, as everywhere else (`is_current_coordinator`: role `coordinator` and `event.coordinator_id`). After a reassignment, only the new coordinator may cancel. Venue Staff, organisers, other coordinators, leads and admins are refused. A booking with no event has no coordinator, so nobody can cancel it here. *(Q1)*
- **A2 — Which bookings:** `pending`, `tentative` (a hold, expired or not) and `confirmed` can be cancelled. `rejected` and `cancelled` can't (409, `reason: "not_cancellable"`). The event's status and the booking's time don't matter: a booking can be cancelled for a cancelled event, or after its time has started. *(Q2)*
- **A3 — What cancelling changes:**
  - Only the booking's `status` changes, to `cancelled`. The row and every other column, including the request details and any earlier decision or hold, are kept.
  - A cancelled booking blocks nothing (SCRUM-36 A2), so the time it covered is free for conflict checks, the calendar and search.
  - Cancelling a **confirmed** booking at the event's venue also clears the event's venue (`events.venue_id`), which approving had set (SCRUM-40 A4). Otherwise the coordinator's page would still show it as the confirmed venue and offer no new request. Cancelling a pending request or a hold leaves the event as it is. *(Q3)*
  - With the pending request cancelled, the coordinator can request a venue again (SCRUM-39 A6 allows one pending request per event).
- **A4 — Who is notified (AC4):** Venue Staff aren't linked to venues in this model (SCRUM-69 A1), so "Venue Staff for that venue" is every user with the `venue_staff` role. Each gets an in-app notification (kind `venue_booking_cancelled`), saved in the same commit as the cancellation, naming the venue, event, period, the booking's previous status and the coordinator who cancelled. An email to each is queued after the commit. If an email can't be queued, the cancellation still stands and the reply says `email_queued: false`. *(Q4)*
- **A5 — The confirmation step (AC2):** it is on the coordinator's venue request page (`/events/<id>/venue-request`), which already lists the event's saved requests (SCRUM-69). Each pending, tentative or confirmed booking offers **Cancel booking**. That shows, inline, which venue and period will be released, with **Yes, cancel booking** and **Keep booking**. Nothing is sent until the coordinator confirms. The server needs no confirmation flag: the step is a UI safeguard. *(Q5)*
- **A6 — Order of checks (AGENTS.md):** 401 (no valid user) → 404 (unknown booking) → 403 (not the event's current coordinator) → 409 (not cancellable). A refusal never describes the booking to someone who may not see it.
- **A7 — Consistency (AC6):** the booking and its event are locked while the cancellation is saved, so a cancellation and a Venue Staff decision on the same booking happen one at a time. The status change, the event's venue and the notifications are saved in one commit. Any database failure rolls everything back and returns 503 with `retryable: true`, leaving the booking as it was.

## Endpoint under test

`POST /api/venues/bookings/<id>/cancel` (no body)

- **200** `{"message", "booking": <the event's saved-request payload (SCRUM-69)>, "notification": {"in_app": true, "email_queued": bool}}`, with the booking's `status` now `cancelled`.
- **401** session · **404** unknown booking · **403** not the event's current coordinator · **409** `reason: "not_cancellable"` · **503** `retryable: true`.

## Seed data (CB-SEED)

SCRUM-40's VA-SEED (`ApprovalTestCase`: users, venues, events E1–E3 approved and organised by dana, P1 and P2 pending), plus these bookings for E1 (Harbour Lights Festival, coordinator alice):

| ID | Venue | Status | Period (Singapore time) | Notes |
|----|-------|--------|-------------------------|-------|
| P1 | Aurora Ballroom | pending | 12 Mar 2027 16:00–22:30 | VA-SEED |
| C1 | Civic Hall | confirmed | 12 Mar 2027 16:00–22:30 | Approved by gus; E1's venue is Civic Hall |
| T1 | Aurora Ballroom | tentative | 13 Mar 2027 09:00–12:00 | Held by gus until 1 Mar 2027 12:00 |
| R1 | Civic Hall | rejected | 11 Mar 2027 10:00–12:00 | Rejected by gus, "No stage power." |
| X1 | Bayfront Pavilion | cancelled | 11 Mar 2027 13:00–15:00 | Cancelled earlier |

P2 is E2's (coordinator ben). Reset the database to this data before every test case.

## Test cases

### AC1 — Only the event's coordinator, and only a live booking

**TC-94-01 · The coordinator cancels a pending request**
- **Traces to:** AC1, AC3 · **Type:** Happy path
- **Steps:** As `alice`, cancel P1.
- **Expected result:** HTTP 200 with a message naming the venue and event. The booking comes back with `status: "cancelled"` and its request details.
- **Automated:** `test_coordinator_cancels_a_pending_request`

**TC-94-02 · A hold and a confirmed booking can be cancelled too**
- **Traces to:** AC1, AC3 · **Type:** Happy path
- **Steps:** As `alice`, cancel T1, then C1.
- **Expected result:** Both give HTTP 200 and are saved as `cancelled`.
- **Automated:** `test_hold_and_confirmed_booking_can_be_cancelled`

**TC-94-03 · Rejected and cancelled bookings can't be cancelled**
- **Traces to:** AC1 · **Type:** Negative
- **Steps:** As `alice`, cancel R1, then X1.
- **Expected result:** HTTP 409 with `reason: "not_cancellable"` and a message giving the current status. Neither booking changes, and no one is notified.
- **Automated:** `test_rejected_and_cancelled_bookings_cannot_be_cancelled`

**TC-94-04 · Anyone but the event's coordinator is refused**
- **Traces to:** AC1 · **Type:** Negative
- **Steps:** Cancel P1 and C1 as `ben` (another event's coordinator), `gus` (Venue Staff), `dana` (the organiser), `admin` and `farah` (attendee).
- **Expected result:** HTTP 403 every time, with no booking details in the reply. Nothing changes, and no one is notified.
- **Automated:** `test_anyone_but_the_events_coordinator_is_refused`

**TC-94-05 · After a reassignment, only the new coordinator may cancel**
- **Traces to:** AC1 · **Type:** Negative
- **Preconditions:** E1 is reassigned from `alice` to `chloe`.
- **Steps:** As `alice`, cancel P1. Then as `chloe`.
- **Expected result:** `alice` gets HTTP 403 and P1 is unchanged; `chloe`'s cancellation succeeds.
- **Automated:** `test_only_the_current_coordinator_may_cancel`

**TC-94-06 · Unknown bookings and invalid sessions**
- **Traces to:** AC1 · **Type:** Negative
- **Steps:** Cancel a booking ID that doesn't exist, as `alice` and as `ben`. Cancel P1 with no token, and with a token for a user that doesn't exist.
- **Expected result:** HTTP 404 for the unknown booking (for both, so the order of checks gives nothing away); HTTP 401 for the invalid sessions. P1 is unchanged.
- **Automated:** `test_unknown_booking_and_invalid_sessions`

### AC2 — Confirmation step (frontend)

**TC-94-07 · The page lists the event's bookings with a Cancel action**
- **Traces to:** AC2 · **Type:** Frontend
- **Steps:** As `alice`, open E1's venue request page.
- **Expected result:** Under "Venue bookings", P1, T1, C1 and X1 are listed with their venue, period and status. P1, T1 and C1 offer **Cancel booking**; X1 doesn't. R1 stays under "Previous venue decisions" with its reason.
- **Automated:** "lists the event's bookings and offers to cancel only the live ones"

**TC-94-08 · Backing out of the confirmation changes nothing**
- **Traces to:** AC2 · **Type:** Frontend
- **Steps:** Choose **Cancel booking** on C1, then **Keep booking**.
- **Expected result:** The confirmation names Civic Hall and its period, and says the venue will be released. After **Keep booking** it closes, nothing is sent, and C1 is still listed as Confirmed.
- **Automated:** "asks for confirmation and sends nothing when the coordinator keeps the booking"

**TC-94-09 · Confirming cancels the booking and shows the result**
- **Traces to:** AC2, AC3 · **Type:** Frontend
- **Steps:** Choose **Cancel booking** on C1, then **Yes, cancel booking**.
- **Expected result:** `POST /venues/bookings/<C1>/cancel` is sent once. The server's message is shown, the page reloads the event and its bookings, and C1 is listed as Cancelled.
- **Automated:** "cancels the booking on confirmation and shows it as cancelled"

### AC3 — Cancelled, kept, and the venue released

**TC-94-10 · The record is kept with only its status changed**
- **Traces to:** AC3 · **Type:** Happy path
- **Steps:** As `alice`, cancel C1.
- **Expected result:** The same row now has status `cancelled`. Every other column is unchanged, including its request details and gus's approval (`decided_at`, `decided_by_id`). No booking is added or removed.
- **Automated:** `test_record_is_kept_with_only_its_status_changed`

**TC-94-11 · The venue slot is free again**
- **Traces to:** AC3 · **Type:** Happy path
- **Preconditions:** At Civic Hall on 3 Apr 2027, E3 has a confirmed booking (18:00–20:00) in one run and an unexpired hold (18:00–20:00) in another, so approving E2's P2 (17:00–21:30) is refused as a clash. (P1 isn't used: E1 already has a confirmed venue, C1, which SCRUM-40 A3 treats as a conflict.)
- **Steps:** As `alice` (E3's coordinator), cancel E3's booking. As `gus`, approve P2.
- **Expected result:** Before cancelling, P2's approval is refused with that conflict. After cancelling, P2's pending-list conflicts are empty and its approval succeeds.
- **Automated:** `test_cancelling_a_confirmed_booking_frees_the_venue_slot`, `test_cancelling_a_hold_frees_the_venue_slot`

**TC-94-12 · Cancelling the confirmed venue clears the event's venue (A3)**
- **Traces to:** AC3 · **Type:** Happy path
- **Steps:** As `alice`, cancel T1, then P1, then C1, checking E1's planning view after each.
- **Expected result:** E1's venue stays Civic Hall after T1 and P1 are cancelled, and is not recorded (`venue: null`) once C1 is cancelled. E1's other fields and status are unchanged.
- **Automated:** `test_cancelling_the_confirmed_venue_clears_the_events_venue`

**TC-94-13 · With its pending request cancelled, the event can request a venue again**
- **Traces to:** AC3 · **Type:** Happy path
- **Steps:** As `alice`, cancel P1, then submit a new request for E1 at Bayfront Pavilion.
- **Expected result:** The new request is created (HTTP 201) as pending.
- **Automated:** `test_event_can_request_a_venue_again_after_cancelling_its_pending_request`

### AC4 — Venue Staff are notified

**TC-94-14 · Every Venue Staff member is notified in-app and by email**
- **Traces to:** AC4 · **Type:** Happy path
- **Preconditions:** A second Venue Staff member, `vera`, is added.
- **Steps:** As `alice`, cancel C1.
- **Expected result:** `gus` and `vera` each have one notification of kind `venue_booking_cancelled` for E1. It names Civic Hall, Harbour Lights Festival, the period, that it was confirmed, and `alice`. An email to each is queued after the commit. The reply says `{"in_app": true, "email_queued": true}`.
- **Automated:** `test_venue_staff_are_notified_in_app_and_by_email`

**TC-94-15 · An email that can't be queued doesn't undo the cancellation**
- **Traces to:** AC4, AC6 · **Type:** Negative (failure)
- **Steps:** With the email queue unreachable, cancel P1 as `alice`.
- **Expected result:** HTTP 200, P1 is cancelled, gus's in-app notification is saved, and the reply says `email_queued: false`.
- **Automated:** `test_email_queue_failure_does_not_undo_the_cancellation`

### AC5 — The event's other bookings are unchanged

**TC-94-16 · Cancelling one booking leaves the others as they were**
- **Traces to:** AC5 · **Type:** Happy path
- **Steps:** As `alice`, cancel C1. Separately (after a reset), cancel P1.
- **Expected result:** Every column of the event's other bookings (P1 or C1, T1, R1, X1) and of E2's P2 is unchanged.
- **Automated:** `test_other_bookings_are_unchanged`

### AC6 — A failed save changes nothing

**TC-94-17 · The cancellation can't be saved**
- **Traces to:** AC6 · **Type:** Negative (failure)
- **Steps:** With the commit failing, cancel C1 as `alice`.
- **Expected result:** HTTP 503 with `retryable: true` and a message saying the booking is unchanged. C1 and E1 are unchanged, no notification is saved and no email is queued.
- **Automated:** `test_failed_save_leaves_the_booking_unchanged`

**TC-94-18 · A notification can't be saved**
- **Traces to:** AC4, AC6 · **Type:** Negative (failure)
- **Steps:** With every notification INSERT failing, cancel P1 as `alice`.
- **Expected result:** As TC-94-17: HTTP 503, P1 unchanged, nothing announced.
- **Automated:** `test_failed_notification_leaves_the_booking_unchanged`

**TC-94-19 · The booking can't be read**
- **Traces to:** AC6 · **Type:** Negative (failure)
- **Steps:** With reading the booking failing, cancel P1 as `alice`.
- **Expected result:** HTTP 503 with `retryable: true`, not 404. P1 is unchanged.
- **Automated:** `test_failed_read_is_reported_not_treated_as_missing`

**TC-94-20 · Cancelling twice keeps the first cancellation**
- **Traces to:** AC1, AC6 · **Type:** Negative
- **Steps:** As `alice`, cancel P1 twice.
- **Expected result:** The second gives HTTP 409 (`not_cancellable`). Venue Staff were notified once.
- **Automated:** `test_cancelling_twice_keeps_the_first_cancellation`

**TC-94-21 · The page shows why cancelling failed and allows another try (frontend)**
- **Traces to:** AC6 · **Type:** Frontend
- **Steps:** Confirm cancelling C1 while the server replies 503 `retryable: true`.
- **Expected result:** The server's message is shown. C1 is still listed as Confirmed and can be cancelled again.
- **Automated:** "shows the error and keeps the booking when cancelling fails"

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 03, 04, 05, 06, 20 |
| AC2 | 07, 08, 09 |
| AC3 | 01, 02, 09, 10, 11, 12, 13 |
| AC4 | 14, 15, 18 |
| AC5 | 16 |
| AC6 | 15, 17, 18, 19, 20, 21 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 02, 10, 11, 12, 13, 14, 16 |
| Negative | 03, 04, 05, 06, 15, 17, 18, 19, 20 |
| Frontend | 07, 08, 09, 21 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Should anyone besides the event's coordinator (e.g. the organiser, or a coordinator lead) be able to cancel a booking? Assumed not. | A1, TC-94-04, 05 |
| Q2 | Can a booking be cancelled after its time has started, or for a cancelled event? Assumed yes: the story sets no time limit. | A2 |
| Q3 | When the event's confirmed venue is cancelled, should the event's venue be cleared (assumed), or kept until a change request? | A3, TC-94-12 |
| Q4 | Venue Staff aren't assigned to venues yet. Is "Venue Staff for that venue" every Venue Staff member (assumed), or should staff be linked to venues? Should the coordinator also be told? | A4, TC-94-14 |
| Q5 | Should cancelling ask for a reason, as rejecting does (SCRUM-69)? Assumed not: the story asks only for a confirmation step. | A5, TC-94-08, 09 |
