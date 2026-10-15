# SCRUM-40 — Approve a Venue Booking Request: Test Cases

**User story:** As a Venue Staff member, I want to approve a pending venue booking request so that the Event Coordinator knows that the proposed venue arrangement can proceed.

**Created:** 15 Oct 2026 · **Status of all cases:** Automated cases pass (15 Oct 2026, local PostgreSQL with db/venue_booking_decisions.sql applied + Vitest); frontend cases 02, 23, 24, 26 and 29 also to be checked manually in the browser · **Automated tests:** `backend/tests/test_venue_booking_approval.py`, `frontend/src/pages/VenueBookingRequestsPage.test.jsx`, `frontend/src/pages/VenueBookingRequestPage.test.jsx` · **Builds on:** SCRUM-39 (booking requests), SCRUM-36 (availability rule)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | Venue Staff can view pending requests, including the event, venue, requested date and start/end times, and venue requirements. |
| AC2 | Only a request currently in Pending status can receive an approval decision. |
| AC3 | Before approval is completed, the system checks that the booking does not create a prohibited conflict. |
| AC4 | Successful approval records a confirmed booking for the requested event and period and makes the decision visible to the coordinator. |
| AC5 | If approval is blocked by a conflict, the request remains unapproved and the conflict is explained. |
| AC6 | If saving the decision fails, the existing request and booking state remain unchanged and an error is displayed. |

## Working assumptions

These are the team's current reading of the story, agreed with the scrum lead on 15 Oct 2026. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Who may approve:** only users with the `venue_staff` role, the same Venue Staff who see the requests (SCRUM-39 A8). This is checked against the database on every request. *(Q1)*
- **A2 — Prohibited conflicts:**
  - A request conflicts when its period overlaps a **confirmed booking** or a **recorded block** at the same venue. This is the rule the SCRUM-36 calendar uses to show time as unavailable.
  - Periods are half-open, so touching periods do not overlap.
  - Pending, rejected and cancelled bookings do not conflict.
  - Operating hours, capacity and the "not currently bookable" flag are suitability, a separate core feature, and do not block approval. *(Q2)*
- **A3 — One confirmed venue per event:** approving a request for an event that already has a confirmed booking (at any venue) is a conflict. Changing an event's venue goes through change requests (SCRUM-52 treats the venue as a restricted field). *(Q3)*
- **A4 — The event must still be able to proceed:** approval is refused if the event is no longer `approved` (for example, it was cancelled after the request), or if the requested start has already passed (Singapore time). *(Q4)*
- **A5 — What approval records:**
  - The booking becomes `confirmed`, with the decision time (naive UTC) and the approving Venue Staff member.
  - The event's venue is set to the approved venue. Its status is unchanged (still `approved`); moving it on is left to Event Status Management.
  - Other pending requests that overlap stay pending. Approving them later is refused as a conflict (A2). *(Q5)*
- **A6 — Visibility to the coordinator:**
  - The event's current coordinator gets an in-app notification (kind `venue_booking_approved`), saved in the same commit as the decision.
  - An email is then queued through Celery. If the email cannot be queued, the approval still stands and the response says so (as in SCRUM-31/32).
  - The planning view shows the approved venue.
  - The coordinator's venue request page shows the confirmed venue instead of offering a new request. *(Q6)*
- **A7 — Concurrent approvals:** the booking's row and its venue's row are locked while a decision is made (`SELECT … FOR UPDATE`). So two staff approving the same request, or overlapping requests for one venue, are handled one at a time, and the second sees the first's result.
- **A8 — Order of checks:**
  1. not logged in (401);
  2. not Venue Staff (403);
  3. unknown booking (404);
  4. booking not pending (409);
  5. event not approved (409);
  6. requested start passed (409);
  7. conflicts, including the event already having a confirmed venue (409, all listed together).

## Endpoint under test

- **`POST /api/venues/bookings/<id>/approve`** (no body)
  - **200** `{"message", "booking": booking + {"decided_at", "decided_by": {"id", "email"}}, "notification": {"in_app": true, "email_queued": bool}}`.
  - **409** `{"error", "reason": "not_pending" | "event_not_approved" | "already_started" | "conflict", "conflicts": [...]}`, where `conflicts` is present for `conflict` only.
  - **503** `{"error", "retryable": true}` if saving fails.
- **A conflict** is one of:
  - `{"type": "booking", "id", "start", "end", "event": {"id", "title"} | null}`, another confirmed booking at the venue;
  - `{"type": "block", "id", "start", "end", "reason"}`, a recorded block at the venue;
  - `{"type": "event_booking", "id", "start", "end", "venue": {"id", "name"}}`, the event's existing confirmed booking.

  They are listed in order of start time.
- `booking` is SCRUM-39's booking payload.

## Seed data (VA-SEED)

Reset the database to this data before **every** test case.
- Users and venues come from `backend/tests/seed_data.py`: gus (venue staff), alice and ben (coordinators), dana (organiser), hana (tech staff), farah (attendee) and admin; Aurora Ballroom (Mon–Sun 08:00–23:00, capacity 400), Civic Hall (Mon–Fri 09:00–18:00, capacity 80) and Dockside Studio (not currently bookable).
- The events and bookings below are created in the test file.

| Ref | Event | Coordinator | Status |
|-----|-------|-------------|--------|
| E1 | Harbour Lights Festival (attendance 250) | alice | approved |
| E2 | Winter Networking Night | ben | approved |
| E3 | Product Launch | alice | approved |

| Ref | Booking | Event | Venue | Status | Period (Singapore time) |
|-----|---------|-------|-------|--------|-------------------------|
| P1 | the request under test | E1 | Aurora Ballroom | pending | Fri 12 Mar 2027 16:00–22:30 |
| P2 | another request | E2 | Civic Hall | pending | Sat 3 Apr 2027 17:00–21:30 |

Further confirmed, rejected or cancelled bookings and blocks are added by the cases that need them.

---

## AC1 — Venue Staff view pending requests

**TC-40-01 · Pending requests show what Venue Staff need**
- **Traces to:** AC1 · **Type:** Happy path (regression)
- **Expected result:** The list shows each pending request's event, venue, requested start and end, and requirements.
- **Automated:** already built and tested by SCRUM-39: TC-39-17 (`test_venue_staff_see_pending_requests`) and TC-39-20 (`VenueBookingRequestsPage.test.jsx`). Re-run as regression.

**TC-40-02 · Each pending request offers Approve**
- **Traces to:** AC1, AC2 · **Type:** Happy path (frontend)
- **Expected result:** Each listed request has an "Approve" button naming its event.

## AC2 — Only pending requests can be approved

**TC-40-03 · A request that is not pending cannot be approved**
- **Traces to:** AC2 · **Type:** Negative (business rule)
- **Steps:** As `gus`, approve a booking that is confirmed, one that is rejected, and one that is cancelled.
- **Expected result:** HTTP 409 with `reason: "not_pending"` and a message naming the status. Nothing changes, and nobody is notified.

**TC-40-04 · Approving twice**
- **Traces to:** AC2 · **Type:** Negative
- **Steps:** As `gus`, approve P1, then approve P1 again.
- **Expected result:** The second call gives HTTP 409 (`not_pending`). P1 keeps its first decision time and approver. alice has exactly one notification, and one email was queued.

**TC-40-05 · Only Venue Staff can approve**
- **Traces to:** AC2 · **Type:** Negative (authorisation) · **Depends on:** Q1
- **Steps:** Approve P1 as alice, dana, hana, farah and admin.
- **Expected result:** HTTP 403 for each. P1 stays pending, E1's venue is not set, and nobody is notified.

**TC-40-06 · A valid session is required**
- **Traces to:** AC2 · **Type:** Negative (authentication)
- **Steps:** Approve P1 with no token, an expired token, and a token for a deleted user.
- **Expected result:** HTTP 401 each time. P1 stays pending.

**TC-40-07 · Unknown booking**
- **Traces to:** AC2 · **Type:** Negative
- **Expected result:** Approving a booking ID that does not exist gives HTTP 404, "Booking request not found."

## AC3 — Conflicts are checked before approval

**TC-40-08 · An overlapping confirmed booking blocks approval**
- **Traces to:** AC3, AC5 · **Type:** Negative (conflict)
- **Preconditions:** E3 has a confirmed booking at Aurora Ballroom, 12 Mar 2027 18:00–20:00.
- **Expected result:** HTTP 409 with `reason: "conflict"`. `conflicts` lists that booking (type `booking`, its times, and event E3 by ID and title). The message says the booking clashes.

**TC-40-09 · An overlapping block blocks approval**
- **Traces to:** AC3, AC5 · **Type:** Negative (conflict)
- **Preconditions:** Aurora Ballroom has a block "Electrical works", 12 Mar 2027 15:00–17:00.
- **Expected result:** HTTP 409 with `reason: "conflict"`. `conflicts` lists the block (type `block`, its times and reason).

**TC-40-10 · Every conflict is listed, in time order**
- **Traces to:** AC3, AC5 · **Type:** Negative (conflict)
- **Preconditions:** Both of the above.
- **Expected result:** HTTP 409. `conflicts` lists the block (15:00) first, then the booking (18:00).

**TC-40-11 · Periods that only touch do not conflict**
- **Traces to:** AC3 · **Type:** Boundary
- **Preconditions:** A confirmed booking at Aurora 12:00–16:00 (ends as P1 starts) and a block 22:30–23:00 (starts as P1 ends).
- **Expected result:** P1 is approved (HTTP 200).

**TC-40-12 · Pending, rejected and cancelled bookings do not conflict**
- **Traces to:** AC3 · **Type:** Boundary · **Depends on:** Q2
- **Preconditions:** Overlapping bookings at Aurora with each of those statuses, for other events.
- **Expected result:** P1 is approved.

**TC-40-13 · Another venue's bookings and blocks do not conflict**
- **Traces to:** AC3 · **Type:** Negative
- **Preconditions:** A confirmed booking and a block at Civic Hall over P1's period.
- **Expected result:** P1 (Aurora) is approved.

**TC-40-14 · Suitability does not block approval**
- **Traces to:** AC3 · **Type:** Boundary · **Depends on:** Q2
- **Steps:** Approve P2 (Civic Hall on a Saturday, outside its Mon–Fri hours). Separately, approve a request for E1 (attendance 250) at Civic Hall (capacity 80), and one at Dockside Studio (not currently bookable).
- **Expected result:** Each is approved. These are suitability matters, not prohibited conflicts.

**TC-40-15 · An event can have only one confirmed venue**
- **Traces to:** AC3, AC5 · **Type:** Negative (conflict) · **Depends on:** Q3
- **Preconditions:** E1 already has a confirmed booking at Civic Hall (12 Mar 2027 16:00–22:30).
- **Expected result:** Approving P1 gives HTTP 409 (`conflict`). `conflicts` includes an `event_booking` entry naming Civic Hall and its times.

**TC-40-16 · Decisions on the same venue are made one at a time**
- **Traces to:** AC3 · **Type:** Concurrency · **Depends on:** A7
- **Steps:** Approve P1 while recording the SQL the request runs.
- **Expected result:** The booking's row and the venue's row are both read with `FOR UPDATE` before the conflict check. So a simultaneous approval of the same request, or of an overlapping request for the same venue, waits and then sees this decision.

## AC4 — Approval confirms the booking and is visible to the coordinator

**TC-40-17 · Approving confirms the booking and records the decision**
- **Traces to:** AC4 · **Type:** Happy path
- **Steps:** As `gus`, approve P1.
- **Expected result:**
  - HTTP 200. P1 is `confirmed`, with its event, venue and period unchanged.
  - `decided_at` is between just before and just after the call, and `decided_by` is gus.
  - The response's `booking` shows all of this, and the message names the venue, the event and the coordinator notified.

**TC-40-18 · The event's venue is set; its status is unchanged**
- **Traces to:** AC4 · **Type:** Happy path · **Depends on:** Q5
- **Steps:** Approve P1, then reload E1 and open its planning view as `alice`.
- **Expected result:** E1's venue is Aurora Ballroom, and its status and other fields are unchanged. The planning view shows Aurora Ballroom as the venue.

**TC-40-19 · The confirmed booking now blocks the venue**
- **Traces to:** AC4 · **Type:** Happy path (integration with SCRUM-36/37/39)
- **Steps:** Approve P1, then:
  - open Aurora's availability for 12 Mar 2027;
  - search venues for 12 Mar 2027 18:00–20:00;
  - list pending requests as `gus`.
- **Expected result:**
  - 16:00–22:30 shows as unavailable, and P1 is listed as a booking.
  - Aurora is not in the search results.
  - P1 is no longer listed as pending.

**TC-40-20 · The coordinator is notified in the app**
- **Traces to:** AC4 · **Type:** Happy path · **Depends on:** Q6
- **Expected result:**
  - alice (E1's current coordinator) has one new notification of kind `venue_booking_approved`, linked to E1, naming Aurora Ballroom, the period and gus.
  - It is in her notifications list.
  - ben, dana and gus get none.

**TC-40-21 · The coordinator is emailed**
- **Traces to:** AC4 · **Type:** Happy path
- **Expected result:** One email is queued to alice, with the event and the venue in the subject. The response has `email_queued: true`.

**TC-40-22 · Email cannot be queued: the approval still stands**
- **Traces to:** AC4 · **Type:** Negative (failure)
- **Preconditions:** Queuing the email raises an error.
- **Expected result:** HTTP 200 with `email_queued: false`. P1 is confirmed, and alice's in-app notification is saved.

**TC-40-23 · Frontend: approving confirms and removes the request**
- **Traces to:** AC4 · **Type:** Happy path (frontend)
- **Expected result:** Clicking Approve sends the approval for that request, shows the server's confirmation, and removes the request from the pending list.

**TC-40-24 · Frontend: the coordinator's request page shows the confirmed venue**
- **Traces to:** AC4 · **Type:** Happy path (frontend) · **Depends on:** Q3
- **Expected result:** When the event already has a venue, the request page shows "Venue confirmed:" with the venue and location, and says changes need a change request. It offers no request form. If the venue's location is not recorded, only the venue's name is shown.

## AC5 — A blocked approval leaves the request unapproved

**TC-40-25 · After a conflict, nothing changes**
- **Traces to:** AC5 · **Type:** Negative (conflict)
- **Steps:** Each of TC-40-08, 09 and 15.
- **Expected result:** P1 stays pending with no decision recorded. E1's venue is unchanged, nobody is notified and no email is queued.

**TC-40-26 · Frontend: the conflict is explained**
- **Traces to:** AC5 · **Type:** Negative (frontend)
- **Expected result:**
  - The server's message is shown, with each conflict on its own line:
    - "Confirmed booking for Product Launch, 2027-03-12 18:00 to 2027-03-12 20:00";
    - "Blocked (Electrical works), 2027-03-12 15:00 to 2027-03-12 17:00";
    - "This event's confirmed booking at Civic Hall, …".
  - The request stays in the list and can be approved again later.

## AC6 — A failed save changes nothing

**TC-40-27 · Saving fails: nothing changes and an error is returned**
- **Traces to:** AC6 · **Type:** Negative (failure)
- **Preconditions:** The commit raises `SQLAlchemyError`.
- **Expected result:**
  - HTTP 503 with `retryable: true`, and an error saying the approval was not saved and to try again.
  - P1 stays pending with no decision, and E1's venue is unchanged.
  - No notification is saved and no email is queued.

**TC-40-28 · Retry succeeds after recovery**
- **Traces to:** AC6 · **Type:** Happy path (recovery)
- **Expected result:** Approving P1 again with the database working succeeds. alice gets exactly one notification.

**TC-40-29 · Frontend: a failure is shown and the request stays**
- **Traces to:** AC6 · **Type:** Negative (frontend)
- **Steps:** Approve when the server returns 503 or 409 (not pending), or when there is no network. Then approve again.
- **Expected result:** The error is shown (the server's message, or one to check the connection and try again). The request stays in the list, and the retry succeeds.

## Other states that prevent approval

**TC-40-30 · The event is no longer approved**
- **Traces to:** AC3 · **Type:** Negative (business rule) · **Depends on:** Q4
- **Preconditions:** E1 is set to cancelled while P1 is still pending.
- **Expected result:** HTTP 409 with `reason: "event_not_approved"` and a message naming the event's status. P1 stays pending.

**TC-40-31 · The requested time has already started**
- **Traces to:** AC3 · **Type:** Negative (business rule) · **Depends on:** Q4
- **Preconditions:** A pending request for E3 at Aurora, 1 Jan 2020 10:00–12:00.
- **Expected result:** HTTP 409 with `reason: "already_started"`. The request stays pending.

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02 |
| AC2 | 02, 03, 04, 05, 06, 07 |
| AC3 | 08, 09, 10, 11, 12, 13, 14, 15, 16, 30, 31 |
| AC4 | 17, 18, 19, 20, 21, 22, 23, 24 |
| AC5 | 08, 09, 10, 15, 25, 26 |
| AC6 | 27, 28, 29 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 02, 17, 18, 19, 20, 21, 23, 24, 28 |
| Negative | 03, 04, 05, 06, 07, 08, 09, 10, 13, 15, 22, 25, 26, 27, 29, 30, 31 |
| Boundary | 11, 12, 14 |
| Concurrency | 16 |
| Cross-cutting (authorisation) | 05, 06 |
| Frontend | 02, 23, 24, 26, 29 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | May only Venue Staff approve (assumed), or also admins? Are venues assigned to particular staff? | A1, TC-40-05 |
| Q2 | Is a conflict only an overlap with a confirmed booking or a block (assumed)? Should operating hours or capacity also block approval? | A2, TC-40-12, 14 |
| Q3 | Can an event hold more than one confirmed venue (e.g. a main hall and a breakout room)? Assumed not. | A3, TC-40-15, 24 |
| Q4 | Should approval be refused for cancelled events, and for periods that have already started (assumed)? | A4, TC-40-30, 31 |
| Q5 | Should approving one request automatically reject other pending requests that now clash? Assumed not: they stay pending. | A5 |
| Q6 | Is an in-app notification plus an email the right way to tell the coordinator (assumed)? Should the organiser also be told? | A6, TC-40-20, 21 |
