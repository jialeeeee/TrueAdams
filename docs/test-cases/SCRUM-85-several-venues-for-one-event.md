# SCRUM-85 — Several Venues for One Event: Test Cases

**User story:** As an Event Coordinator, I want to book more than one venue for the same event so that events needing several spaces can be planned.

**Created:** 27 Oct 2026 · **Branch:** `feature/SCRUM-85-several-venues-for-one-event` · **Source:** Week 7 customer change 3, "Multiple Venues for One Event" (a conference may need one auditorium for the main programme and three smaller rooms for breakout sessions) · **Status of all cases:** written first and failing (TDD, red) · **Automated tests:** `backend/tests/test_several_venues.py`, `frontend/src/pages/EventPlanningPage.test.jsx`, `frontend/src/pages/VenueBookingRequestPage.test.jsx` · **Changes:** SCRUM-39 A6 (one pending request per event), SCRUM-40 A3 (one confirmed venue per event) and SCRUM-41's `event_booking` conflict, which the customer change replaces, and SCRUM-94 A3 (what happens to the event's venue when its booking is cancelled)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | An event can have several venue booking requests, each with its own venue and period. |
| AC2 | Each booking is checked on its own for suitability, availability and conflicts, and is approved or rejected on its own. |
| AC3 | Changing or cancelling one booking leaves the others unchanged unless the coordinator chooses to cancel them too. |
| AC4 | The event's planning view lists all its venue bookings with the status of each. |

## Working assumptions

Each one is tied to an open question below. If the customer answers differently, update the affected test cases before changing the code.

- **A1 — Several requests:** the event's coordinator may request any number of venues for an approved event, whether or not it already has pending, held or confirmed bookings. Each request has its own venue, period, setup and turnaround time and venue requirements (as in SCRUM-39 and SCRUM-84). Several can be pending at once, so SCRUM-39's rule of one pending request per event, and the database index `venue_bookings_one_pending_per_event` that enforced it, are removed (`db/several_venues_per_event.sql`). *(Q1)*
- **A2 — No duplicate requests:** a request is refused (409, `reason: "already_requested"`) when the event already has a **pending** request for the **same venue** whose occupied period (with setup and turnaround, SCRUM-84) overlaps the new one, because Venue Staff would be asked twice for the same thing. A different venue at the same time, the same venue at another time, and a request after the earlier one is decided or cancelled are all allowed. Another event's pending request blocks nothing (SCRUM-36 A2). The event's own confirmed booking or unexpired hold at that venue is already a conflict (SCRUM-84 A5, SCRUM-87 A3). The event row stays locked while this is checked, as in SCRUM-39, so two submissions are checked one at a time. *(Q2)*
- **A3 — Each booking is checked on its own:** approving or holding a booking checks only its own venue and period: confirmed bookings, blocks and unexpired holds there (SCRUM-41, SCRUM-84, SCRUM-87). The event's bookings at other venues are no longer a conflict, so the `event_booking` conflict type is no longer produced. The event's own confirmed booking at the **same** venue and an overlapping time is still a conflict (type `booking`). Rejecting (SCRUM-69) was already per booking. Suitability (SCRUM-38) is already checked one venue at a time, and Venue Staff assess each request against its own venue requirements. *(Q4)*
- **A4 — The event's venue:** `events.venue_id` is kept as the event's **main venue**, the one attendees and registration settings already show (SCRUM-74, SCRUM-45). Approving a booking sets it only when the event has no other confirmed booking, so the first confirmed venue stays the main one. Cancelling a confirmed booking at the main venue moves it to the venue of the event's earliest remaining confirmed booking (by start, then id). If there is none, it is cleared, as SCRUM-94 A3 did. For an event with one venue, nothing changes. *(Q3)*
- **A5 — Changing one booking:** placing a hold on a booking, changing its hold's expiry, approving, rejecting or cancelling it changes only that booking. *(AC3)*
- **A6 — Cancelling others too:** `POST /api/venues/bookings/<id>/cancel` takes an optional body `{"also_cancel": [<booking id>, …]}`: other bookings of the same event the coordinator chose to cancel in the same step. Without it, only the one booking is cancelled (SCRUM-94 AC5). The choice is all or nothing:
  - Anything other than a list of booking ids, or an id that is not one of this event's bookings, gives 400 (`field: "also_cancel"`). An id from another event and an unknown id get the same answer, so nothing is revealed about other events. Any other field gives 400 naming it, as for holds (SCRUM-87).
  - An id that is rejected or already cancelled gives 409, `reason: "not_cancellable"`, naming the status.
  - Any refusal cancels nothing. The main booking is the one in the URL, and repeating its id in the list changes nothing.
  - Every Venue Staff member gets **one** in-app notification and one email naming every booking cancelled, saved in the same commit as the cancellations (SCRUM-94 A4).
  - The reply's `booking` is the main booking, as before, and `also_cancelled` lists the others.
  - Order of checks: 401 → 404 (main booking) → 403 → 400 (body) → 409. *(Q5)*
- **A7 — The planning view:** `GET /api/events/<id>/planning` adds `venue_bookings`, every booking of the event of any status, in time order (start, then id). Each has `id`, `venue` (`id`, `name`, `location`), `start_time`, `end_time`, `setup_minutes`, `turnaround_minutes`, `status`, `hold_expires_at` and `hold_expired`. The last two are only set for a tentative hold: an expired hold blocks nothing (SCRUM-87), so the view says it has expired instead of passing it off as a live hold. A failed read of the bookings is a 503, never an empty list. The planning page lists them under "Venue bookings", or says there are none. *(Q6)*
- **A8 — The coordinator's venue request page:** it offers the request form for an approved event even when a venue is confirmed. After a request is sent, **Request another venue** opens a fresh form. The cancellation step lists the event's other pending, tentative and confirmed bookings, unticked, so the coordinator can choose to cancel them too.

## Seed data (MV-SEED)

SCRUM-94's CB-SEED (`tests/test_venue_booking_cancellation.py`, itself SCRUM-40's VA-SEED): users alice and ben (coordinators) and gus (Venue Staff); venues Aurora Ballroom, Bayfront Pavilion, Civic Hall and Dockside Studio; approved events E1 Harbour Lights Festival (alice), E2 Winter Networking Night (ben) and E3 Product Launch (alice).

| Key | Event | Venue | Status | Period (Singapore time) | Notes |
|-----|-------|-------|--------|-------------------------|-------|
| P1 | E1 | Aurora Ballroom | pending | 2027-03-12 16:00 – 22:30 | |
| C1 | E1 | Civic Hall | confirmed | 2027-03-12 16:00 – 22:30 | E1's venue is Civic Hall |
| T1 | E1 | Aurora Ballroom | tentative | 2027-03-13 09:00 – 12:00 | hold expires 2027-03-01 12:00 |
| R1 | E1 | Civic Hall | rejected | 2027-03-11 10:00 – 12:00 | |
| X1 | E1 | Bayfront Pavilion | cancelled | 2027-03-11 13:00 – 15:00 | |
| P2 | E2 | Civic Hall | pending | 2027-04-03 17:00 – 21:30 | |

Some cases add **C2**, a confirmed booking of E1 at Aurora Ballroom, 2027-03-12 09:00 – 12:00.

---

## AC1 — Several requests, each with its own venue and period

**TC-85-01 · Another venue can be requested while the event has pending, held and confirmed bookings**
- **Traces to:** AC1 · **Type:** Positive · **Depends on:** A1
- **Steps:** As alice, request Bayfront Pavilion for E1, 2027-03-12 16:00 – 22:30.
- **Expected result:** HTTP 201, status pending. E1 now has two pending requests (P1 and the new one); P1, C1 and T1 are unchanged.
- **Automated:** `test_tc_85_01_another_venue_can_be_requested_alongside_existing_bookings`

**TC-85-02 · Each request keeps its own venue, period, setup, turnaround and requirements**
- **Traces to:** AC1 · **Type:** Positive · **Depends on:** A1
- **Steps:** Request Bayfront Pavilion, 2027-03-12 09:00 – 12:00, setup 30, turnaround 15, "Breakout room A"; then Dockside Studio, 2027-03-12 13:00 – 15:00, "Breakout room B".
- **Expected result:** Both 201. Each saved row has exactly the venue, times, minutes and requirements sent.
- **Automated:** `test_tc_85_02_each_request_keeps_its_own_details`

**TC-85-03 · The same venue at an overlapping time as the event's pending request is refused**
- **Traces to:** AC1 · **Type:** Negative (business rule) · **Depends on:** A2
- **Steps:** Request Aurora Ballroom for E1 at 2027-03-12 20:00 – 23:00 (overlaps P1); then 22:45 – 23:30 with 30 minutes' setup (occupies from 22:15); then 22:30 – 23:30 with no setup (only touches P1).
- **Expected result:** The first two are refused with 409, `reason: "already_requested"`, naming Aurora Ballroom; nothing is saved. The third is accepted (201).
- **Automated:** `test_tc_85_03_the_same_venue_at_an_overlapping_time_is_refused`

**TC-85-04 · A decided request, or another event's request, doesn't block the same venue and time**
- **Traces to:** AC1 · **Type:** Positive · **Depends on:** A2
- **Steps:** Request Aurora Ballroom 2027-03-12 16:00 – 22:30 for E3 (alice), while E1's P1 is pending there. Then reject P1 and request the same for E1.
- **Expected result:** Both 201.
- **Automated:** `test_tc_85_04_decided_or_other_events_requests_do_not_block`

**TC-85-05 · The database allows several pending requests for one event**
- **Traces to:** AC1 · **Type:** Data integrity · **Depends on:** A1
- **Steps:** Insert two pending bookings for E3 at different venues and commit.
- **Expected result:** The commit succeeds.
- **Automated:** `test_tc_85_05_the_database_allows_several_pending_requests`

**TC-85-06 · The event is locked before its requests are checked**
- **Traces to:** AC1 · **Type:** Business rule (concurrency) · **Depends on:** A2
- **Steps:** Request Bayfront Pavilion for E1 and record the SQL sent.
- **Expected result:** The event is read `FOR UPDATE` before any venue booking is read.
- **Automated:** `test_tc_85_06_the_event_is_locked_before_its_requests_are_checked`

## AC2 — Each booking is checked, approved and rejected on its own

**TC-85-07 · A second venue is approved while the event has a confirmed one**
- **Traces to:** AC2 · **Type:** Positive · **Depends on:** A3
- **Steps:** As gus, approve P1 (Aurora Ballroom, the same time as E1's confirmed C1 at Civic Hall).
- **Expected result:** HTTP 200; P1 and C1 are both confirmed.
- **Automated:** `test_tc_85_07_a_second_venue_is_approved_alongside_a_confirmed_one`

**TC-85-08 · Venue Staff's list shows no conflict from the event's venue elsewhere**
- **Traces to:** AC2 · **Type:** Positive · **Depends on:** A3
- **Steps:** As gus, list pending requests.
- **Expected result:** P1's `conflicts` is empty.
- **Automated:** `test_tc_85_08_the_events_venue_elsewhere_is_not_a_conflict`

**TC-85-09 · The event's own booking at the same venue still clashes**
- **Traces to:** AC2 · **Type:** Negative (conflict) · **Depends on:** A3
- **Steps:** Add P3, a pending E1 booking at Civic Hall 2027-03-12 20:00 – 23:00 (overlapping C1). Approve P3.
- **Expected result:** HTTP 409 `conflict`, listing only C1, as a `booking` for Harbour Lights Festival. P3 stays pending.
- **Automated:** `test_tc_85_09_the_events_own_booking_at_the_same_venue_still_clashes`

**TC-85-10 · A hold can be placed on a second venue**
- **Traces to:** AC2, AC3 · **Type:** Positive · **Depends on:** A3, A5
- **Steps:** As gus, hold P1 until 2027-03-01 12:00.
- **Expected result:** HTTP 200; P1 is tentative; C1, T1, R1 and X1 and the event are unchanged.
- **Automated:** `test_tc_85_10_a_hold_can_be_placed_on_a_second_venue`

**TC-85-11 · One venue's clash doesn't stop another venue's approval**
- **Traces to:** AC2 · **Type:** Positive · **Depends on:** A3
- **Steps:** Block Aurora Ballroom 2027-03-12 15:00 – 17:00. Add P4, a pending E1 booking at Bayfront Pavilion 2027-03-12 16:00 – 22:30. Approve P1, then P4.
- **Expected result:** P1 is refused (409, the block); P4 is approved (200).
- **Automated:** `test_tc_85_11_one_venues_clash_does_not_stop_another`

**TC-85-12 · Rejecting one request leaves the event's other bookings unchanged**
- **Traces to:** AC2, AC3 · **Type:** Positive · **Depends on:** A5
- **Steps:** Approve P1, add P4 (as TC-85-11) and reject P4.
- **Expected result:** P4 is rejected; P1, C1, T1, R1 and X1 and the event's venue are unchanged.
- **Automated:** `test_tc_85_12_rejecting_one_request_leaves_the_others`

**TC-85-13 · The first confirmed venue stays the event's venue**
- **Traces to:** AC2 · **Type:** Positive · **Depends on:** A4
- **Steps:** Approve P1.
- **Expected result:** E1's venue is still Civic Hall, in the database and the planning view.
- **Automated:** `test_tc_85_13_the_first_confirmed_venue_stays_the_events_venue`

## AC3 — Changing or cancelling one booking leaves the others

**TC-85-14 · Cancelling one of several confirmed bookings leaves the others**
- **Traces to:** AC3 · **Type:** Positive · **Depends on:** A4, A5
- **Steps:** With C2, cancel C2.
- **Expected result:** C2 is cancelled; C1 is still confirmed; E1's venue is still Civic Hall; P1, T1, R1 and X1 are unchanged.
- **Automated:** `test_tc_85_14_cancelling_one_confirmed_booking_leaves_the_others`

**TC-85-15 · Cancelling the main venue moves the event's venue to a remaining one**
- **Traces to:** AC3 · **Type:** Positive · **Depends on:** A4
- **Steps:** With C2, cancel C1; then cancel C2.
- **Expected result:** After C1, E1's venue is Aurora Ballroom (C2's); after C2, it has none.
- **Automated:** `test_tc_85_15_cancelling_the_main_venue_moves_the_events_venue`

**TC-85-16 · The coordinator chooses to cancel other bookings too**
- **Traces to:** AC3 · **Type:** Positive · **Depends on:** A6
- **Steps:** Cancel P1 with `{"also_cancel": [C1, T1]}`.
- **Expected result:** HTTP 200. P1, C1 and T1 are cancelled; R1 and X1 are unchanged. E1 has no venue. `booking` is P1, `also_cancelled` is C1 and T1, and the message names all three venues. gus has one notification naming all three; one email per Venue Staff member is queued.
- **Automated:** `test_tc_85_16_the_coordinator_chooses_to_cancel_others_too`

**TC-85-17 · A refused choice cancels nothing**
- **Traces to:** AC3 · **Type:** Negative · **Depends on:** A6
- **Steps:** Cancel P1 with, in turn: E2's P2; an unknown id; `"C1"` instead of a list; `[true]`; another field; then R1 (rejected). Also, as ben, cancel P1 with an invalid body.
- **Expected result:** 400 with `field: "also_cancel"` for the first four (the same answer for P2 and the unknown id), and naming the other field for the last; 409 `not_cancellable` naming "rejected" for R1; 403 for ben. Nothing is cancelled and nobody is notified.
- **Automated:** `test_tc_85_17_a_refused_choice_cancels_nothing`

**TC-85-18 · Changing one hold's expiry leaves the other bookings**
- **Traces to:** AC3 · **Type:** Positive · **Depends on:** A5
- **Steps:** As gus, change T1's expiry to 2027-03-02 12:00.
- **Expected result:** HTTP 200; P1, C1, R1 and X1 and the event are unchanged.
- **Automated:** `test_tc_85_18_changing_one_hold_leaves_the_others`

**TC-85-19 · A failed save cancels none of them**
- **Traces to:** AC3 · **Type:** Negative (failure) · **Depends on:** A6
- **Steps:** Make the commit fail and cancel P1 with `{"also_cancel": [C1]}`.
- **Expected result:** HTTP 503, `retryable: true`; P1 and C1 and the event unchanged; nobody notified.
- **Automated:** `test_tc_85_19_a_failed_save_cancels_none_of_them`

## AC4 — The planning view lists every booking with its status

**TC-85-20 · The planning view lists every booking with its status, in time order**
- **Traces to:** AC4 · **Type:** Positive · **Depends on:** A7
- **Steps:** As alice, open E1's planning view.
- **Expected result:** `venue_bookings` is R1, X1, P1, C1, T1, each with its venue, times, setup and turnaround, and status. T1 has its `hold_expires_at` and `hold_expired: false`; the others have `null` for both.
- **Automated:** `test_tc_85_20_the_planning_view_lists_every_booking_with_its_status`

**TC-85-21 · An expired hold is shown as expired**
- **Traces to:** AC4 · **Type:** Boundary · **Depends on:** A7
- **Steps:** Set T1's expiry to 2026-01-01 12:00 and open E1's planning view.
- **Expected result:** T1 has `status: "tentative"` and `hold_expired: true`.
- **Automated:** `test_tc_85_21_an_expired_hold_is_shown_as_expired`

**TC-85-22 · Only the event's own bookings are listed, and none is not an error**
- **Traces to:** AC4 · **Type:** Boundary · **Depends on:** A7
- **Steps:** Open E3's planning view (no bookings); check E1's list for E2's P2.
- **Expected result:** E3's `venue_bookings` is `[]`; P2 is not in E1's list.
- **Automated:** `test_tc_85_22_only_the_events_own_bookings_are_listed`

**TC-85-23 · A failed read of the bookings is a failure, not an empty list**
- **Traces to:** AC4 · **Type:** Negative (failure) · **Depends on:** A7
- **Steps:** Make reading venue bookings fail and open E1's planning view.
- **Expected result:** HTTP 503, `retryable: true`, no event details.
- **Automated:** `test_tc_85_23_a_failed_read_is_a_failure_not_an_empty_list`

## Frontend

**TC-85-24 · The planning page lists each booking with its venue, period and status** — AC4 · `EventPlanningPage.test.jsx` "lists every venue booking with its status"

**TC-85-25 · The planning page says when there are no venue bookings** — AC4 · `EventPlanningPage.test.jsx` "says when the event has no venue bookings"

**TC-85-26 · The request page offers another request while a venue is confirmed** — AC1 · `VenueBookingRequestPage.test.jsx` "offers the request form alongside the confirmed venue" (replaces TC-40-24)

**TC-85-27 · After sending, Request another venue opens a fresh form** — AC1 · `VenueBookingRequestPage.test.jsx` "opens a fresh form to request another venue"

**TC-85-28 · Cancelling offers the event's other live bookings, unticked** — AC3 · `VenueBookingRequestPage.test.jsx` "offers the other live bookings and cancels only the chosen one by default"

**TC-85-29 · Ticked bookings are cancelled too** — AC3 · `VenueBookingRequestPage.test.jsx` "cancels the other bookings the coordinator ticks"

---

## Traceability matrix

| AC | Test cases |
|----|------------|
| AC1 | 01, 02, 03, 04, 05, 06, 26, 27 |
| AC2 | 07, 08, 09, 10, 11, 12, 13 |
| AC3 | 10, 12, 14, 15, 16, 17, 18, 19, 28, 29 |
| AC4 | 20, 21, 22, 23, 24, 25 |

## Earlier test cases this story changes

| Case | Was | Now |
|------|-----|-----|
| SCRUM-39 TC-39-23, 25 | A second pending request for an event is refused; the database allows one | TC-85-01, 03, 05 |
| SCRUM-39 TC-39-30 | A save refused by the one-pending index is reported as "already pending" | A refused save is reported as not sent (503), like any other failed save |
| SCRUM-40 TC-40-15 | An event can have only one confirmed venue (`event_booking` conflict) | TC-85-07, 09; TC-40-25 now uses another event's booking at the same venue |
| SCRUM-40 TC-40-24 | The request page shows the confirmed venue instead of a form | TC-85-26 |
| SCRUM-41 TC-41-03 | The event's confirmed venue is listed as a conflict | TC-85-08 |
| SCRUM-94 A3 | Cancelling the confirmed venue clears the event's venue | Still true for an event with one venue; with several, TC-85-15 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Is there a limit to how many venues one event may have, or to how many requests may be pending at once? Assumed not. | A1, TC-85-01, 02 |
| Q2 | May an event ask for the same venue twice at overlapping times while the first request is pending? Assumed not. | A2, TC-85-03 |
| Q3 | Which venue should attendees see, and registration capacity be compared with, when an event has several? Assumed the first one confirmed. | A4, TC-85-13, 15 |
| Q4 | Should a venue's suitability (SCRUM-38) be judged against the event's whole expected attendance, or against how many people use that space (a breakout room holds fewer)? Unchanged for now: the whole attendance. | A3 |
| Q5 | When a coordinator cancels several bookings at once, should one that can't be cancelled stop them all (assumed), or should the rest go ahead? | A6, TC-85-17 |
| Q6 | Should a booking's period have to fall within the event's own start and end? Assumed not, as in SCRUM-39, so setup days and breakout sessions can be booked as needed. | A1, A7 |
