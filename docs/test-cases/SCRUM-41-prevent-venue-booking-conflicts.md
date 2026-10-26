# SCRUM-41 — Prevent Conflicting Venue Bookings: Test Cases

**User story:** As a Venue Staff member, I want conflicts to be identified before a venue booking is confirmed so that the venue is not committed to incompatible events.

**Created:** 16 Oct 2026 · **Reopened:** 26 Oct 2026, AC1 now includes unexpired tentative holds (see the section on the reopening) · **Status of all cases:** Automated cases pass (16 Oct 2026, local PostgreSQL with db/venue_booking_conflicts.sql applied + Vitest; TC-41-18 and 19 on 26 Oct 2026); frontend cases 06, 07 and 17 also to be checked manually in the browser · **Automated tests:** `backend/tests/test_venue_booking_conflicts.py`, `frontend/src/pages/VenueBookingRequestsPage.test.jsx` · **Builds on:** SCRUM-40 (approval and its conflict check), SCRUM-39 (venue requests and Venue Staff's list), SCRUM-36 (availability rule)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The check compares the proposed venue and booking period with confirmed bookings, unexpired tentative holds and recorded periods of unavailability for that venue. *(holds added on reopening, 26 Oct 2026)* |
| AC2 | An incompatible overlap is identified, and the conflicting period is displayed. |
| AC3 | A prohibited overlap prevents confirmation; no new confirmed booking is created. |
| AC4 | Bookings for different venues are not treated as conflicting solely because their times overlap. |
| AC5 | A booking with no prohibited overlap can proceed to confirmation, subject to other approval requirements. |
| AC6 | If competing approvals are attempted, the final save prevents incompatible bookings from both becoming confirmed. |
| AC7 | If the conflict check cannot be completed, confirmation is prevented and the user is informed that availability could not be verified. |

## What SCRUM-40 already provides

SCRUM-40 checks for conflicts when Venue Staff approve a request:
- it refuses the approval (409) and lists every clash with its period (AC1–AC3);
- it ignores other venues (AC4);
- it lets a clear request through, subject to the event and time rules (AC5);
- it locks the booking and venue rows so approvals at one venue happen one at a time (AC6).

Those cases are re-run here as regression and traced to their SCRUM-40 tests. SCRUM-41 adds what the story still needs:
- conflicts identified **before** anyone presses Approve;
- a database rule as the final safeguard;
- a clear message when availability cannot be verified.

## Working assumptions

These are the team's current reading of the story, agreed with the scrum lead on 16 Oct 2026. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — What counts as a conflict:** the SCRUM-40 rule, unchanged.
  - The request's period overlaps a **confirmed booking** or a **recorded block** at the same venue. Periods are half-open, so touching periods do not overlap.
  - The event already has a confirmed booking (at any venue), because an event has one confirmed venue (SCRUM-40 A3).
  - Pending, rejected and cancelled bookings do not conflict. Operating hours, capacity and the "not currently bookable" flag are suitability, not conflicts. *(Q1)*
  - **Since the reopening:** an **unexpired tentative hold** at the same venue conflicts too. A hold is unexpired while its expiry is later than the current Singapore time; at the expiry itself it has expired and no longer conflicts. This is SCRUM-87 A3's rule. *(Q5)*
- **A2 — Conflicts are shown before approval:**
  - Each request in Venue Staff's pending list (`GET /api/venues/bookings`) carries `conflicts`: the same entries, in the same time order, that approving it now would be refused with. An empty list means none were found.
  - The page shows each conflict on its own line with its period (the SCRUM-40 wording), or "No conflicts found."
  - Approve stays available either way. The list can be out of date, and the server checks again when the approval is saved. *(Q2)*
- **A3 — Other venues:** a booking or block at another venue never conflicts because of its times (AC4). The only cross-venue conflict is A1's "the event already has a confirmed venue", which is about the event and applies whatever the times. *(Q1)*
- **A4 — The final save (AC6):** two safeguards.
  - The SCRUM-40 row locks make approvals at one venue happen one at a time.
  - A new database rule, `venue_bookings_no_overlapping_confirmed`, refuses to store two **confirmed** bookings at the same venue whose periods overlap (half-open, so touching is allowed). It holds even for a code path that does not take the lock.
  - If the rule refuses an approval's save, the reply is the usual conflict refusal (409, `reason: "conflict"`) listing the clash. Nothing is changed, and nobody is notified.
  - Blocks are stored in another table, so the rule cannot cover them. A clash with a block relies on the lock. *(Q3)*
- **A5 — The check cannot be completed (AC7):**
  - **Approving:** if the database fails while the venue is locked or its conflicts are checked, the booking is not confirmed. The reply is 503 with `retryable: true` and a message saying availability could not be verified. This is separate from SCRUM-40's "the approval was not saved", which covers a failure at the save itself.
  - **The list:** if the conflicts cannot be checked, the whole list fails with a message saying availability could not be verified. Requests are never shown as having no conflicts when that was not checked. *(Q4)*
- **A6 — The list stays current after an approval:** after an approval succeeds, the page reloads the list, so the remaining requests show any clash with the booking just confirmed. *(Q2)*

## Endpoints under test

- **`GET /api/venues/bookings`** (SCRUM-39, Venue Staff only)
  - **200** `{"bookings": [booking + {"conflicts": [...]}], "message"}`. Each `conflicts` list has the SCRUM-40 conflict entries, in time order; it is `[]` when none were found.
  - **503** `{"error", "retryable": true}`. The error says "could not be loaded" if the requests themselves could not be read (SCRUM-39), or that availability could not be verified if their conflicts could not be checked (A5).
- **`POST /api/venues/bookings/<id>/approve`** (SCRUM-40). New replies:
  - **409** `{"error", "reason": "conflict", "conflicts": [...]}` when the database rule refuses the save (A4).
  - **503** `{"error", "retryable": true}` saying availability could not be verified, when the conflict check fails (A5).
- **A conflict entry** is one of the SCRUM-40 types:
  - `{"type": "booking", "id", "start", "end", "event": {"id", "title"} | null}`;
  - `{"type": "block", "id", "start", "end", "reason"}`;
  - `{"type": "event_booking", "id", "start", "end", "venue": {"id", "name"}}`.

## Seed data (VC-SEED)

Reset the database to this data before **every** test case.
- VC-SEED is SCRUM-40's VA-SEED. The users and venues come from `backend/tests/seed_data.py`:
  - users: gus (venue staff), alice and ben (coordinators), dana (organiser);
  - venues: Aurora Ballroom, Civic Hall and Dockside Studio.
- Approved events: E1 Harbour Lights Festival (alice), E2 Winter Networking Night (ben) and E3 Product Launch (alice).
- Pending requests:
  - P1: E1 at Aurora Ballroom, Fri 12 Mar 2027 16:00–22:30;
  - P2: E2 at Civic Hall, Sat 3 Apr 2027 17:00–21:30.
- The cases add any further bookings and blocks they need.

---

## AC1, AC2 — Conflicts are identified and shown before approval

**TC-41-01 · A request with no conflicts is listed as having none**
- **Traces to:** AC2, AC5 · **Type:** Happy path
- **Steps:** As `gus`, list the pending requests.
- **Expected result:** P1 and P2 are listed, each with `conflicts: []`.
- **Automated:** `test_request_without_conflicts_lists_none`

**TC-41-02 · Overlapping confirmed bookings and blocks at the venue are listed with their periods**
- **Traces to:** AC1, AC2 · **Type:** Negative (conflict)
- **Preconditions:**
  - E3 has a confirmed booking at Aurora Ballroom, 12 Mar 2027 18:00–20:00.
  - Aurora Ballroom has a block "Electrical works", 12 Mar 2027 15:00–17:00.
- **Steps:** As `gus`, list the pending requests.
- **Expected result:**
  - P1's `conflicts` lists the block first, then the booking, each with its start and end. The booking names E3; the block gives its reason.
  - P2's `conflicts` is empty.
- **Automated:** `test_overlapping_bookings_and_blocks_are_listed_with_their_periods`

**TC-41-03 · The event's existing confirmed venue is listed**
- **Traces to:** AC1, AC2 · **Type:** Negative (conflict) · **Depends on:** Q1
- **Preconditions:** E1 already has a confirmed booking at Civic Hall, 12 Mar 2027 16:00–22:30.
- **Expected result:** P1's `conflicts` lists that booking (type `event_booking`, its times and Civic Hall).
- **Automated:** `test_events_existing_confirmed_venue_is_listed`

**TC-41-04 · Only confirmed bookings and blocks that really overlap are listed**
- **Traces to:** AC1 · **Type:** Boundary · **Depends on:** Q1
- **Preconditions:**
  - A confirmed booking at Aurora ends exactly at 16:00, and a block starts exactly at 22:30.
  - E3 has pending, rejected and cancelled bookings at Aurora, 18:00–20:00.
- **Expected result:** P1's `conflicts` is empty.
- **Automated:** `test_touching_and_unconfirmed_bookings_are_not_listed`

**TC-41-05 · Bookings and blocks at other venues are not listed**
- **Traces to:** AC4 · **Type:** Boundary
- **Preconditions:** E3 has a confirmed booking at Civic Hall, and Civic Hall has a block, both 12 Mar 2027 16:00–22:30.
- **Expected result:** P1's `conflicts` is empty.
- **Automated:** `test_other_venues_are_not_listed_as_conflicts`

**TC-41-06 · Frontend: each request shows its conflicts with their periods**
- **Traces to:** AC2 · **Type:** Happy path (frontend)
- **Steps:** Open the venue requests page. P1 has a block and a confirmed booking as conflicts; P2 has none.
- **Expected result:**
  - Under P1, one line per conflict, using the SCRUM-40 wording:
    - "Blocked (Electrical works), 2027-03-12 15:00 to 2027-03-12 17:00";
    - "Confirmed booking for Product Launch, 2027-03-12 18:00 to 2027-03-12 20:00".
  - Under P2: "No conflicts found."
  - Both keep their Approve buttons.
- **Automated:** "shows each request's conflicts with their periods" (`VenueBookingRequestsPage.test.jsx`)

**TC-41-07 · Frontend: the list is reloaded after an approval**
- **Traces to:** AC2 · **Type:** Happy path (frontend) · **Depends on:** Q2
- **Steps:** Approve P1. The reloaded list shows P2 clashing with P1's confirmed booking.
- **Expected result:**
  - The list is requested again after the approval.
  - P2 now shows "Confirmed booking for Harbour Lights Festival, …".
  - P1 is no longer listed.
- **Automated:** "reloads the list after an approval so new clashes show" (`VenueBookingRequestsPage.test.jsx`)

## AC1–AC5 — Approval refuses conflicts and allows the rest (regression)

**TC-41-08 · A conflict prevents confirmation and is explained**
- **Traces to:** AC1, AC2, AC3 · **Type:** Negative (regression)
- **Expected result:** Approving a request that overlaps a confirmed booking or a block at its venue gives 409 (`conflict`) and lists each clash with its period. The request stays pending, and no confirmed booking is created.
- **Automated:** SCRUM-40 TC-40-08, 09, 10, 15 and 26 (`test_overlapping_confirmed_booking_blocks_approval`, `test_overlapping_block_blocks_approval`, `test_every_conflict_is_listed_in_time_order`, `test_event_can_have_only_one_confirmed_venue`, and "explains each conflict and keeps the request pending").

**TC-41-09 · Overlapping times at other venues do not prevent approval**
- **Traces to:** AC4 · **Type:** Boundary (regression)
- **Automated:** SCRUM-40 TC-40-13 (`test_another_venues_bookings_and_blocks_do_not_conflict`).

**TC-41-10 · A request with no prohibited overlap is confirmed, subject to the other rules**
- **Traces to:** AC5 · **Type:** Happy path (regression)
- **Expected result:**
  - With no clash, approval confirms the booking.
  - Touching periods and unconfirmed bookings do not block it.
  - The other approval rules still apply: the request must be pending, the event approved, and the start not passed.
- **Automated:** SCRUM-40 TC-40-11, 12, 17, 03, 30 and 31 (`test_periods_that_only_touch_do_not_conflict`, `test_bookings_that_are_not_confirmed_do_not_conflict`, `test_approving_confirms_the_booking_and_records_the_decision`, `test_request_that_is_not_pending_cannot_be_approved`, `test_event_no_longer_approved_blocks_approval`, `test_requested_time_already_started_blocks_approval`).

## AC6 — Competing approvals cannot both be confirmed

**TC-41-11 · Approvals at one venue are made one at a time**
- **Traces to:** AC6 · **Type:** Concurrency (regression)
- **Automated:** SCRUM-40 TC-40-16 (`test_booking_and_venue_rows_are_locked_before_the_conflict_check`).

**TC-41-12 · The database refuses two overlapping confirmed bookings at one venue**
- **Traces to:** AC6 · **Type:** Negative (data integrity) · **Depends on:** Q3
- **Preconditions:** E3 has a confirmed booking at Aurora Ballroom, 12 Mar 2027 18:00–20:00.
- **Steps:** Save P1 as confirmed directly, without going through the approval endpoint.
- **Expected result:** The database refuses the save (`IntegrityError`).
- **Automated:** `test_database_refuses_overlapping_confirmed_bookings`

**TC-41-13 · The database rule allows everything that is not a conflict**
- **Traces to:** AC4, AC5, AC6 · **Type:** Boundary · **Depends on:** Q3
- **Steps:** Save each of these as confirmed directly:
  - a booking that only touches E3's confirmed booking;
  - an overlapping confirmed booking at another venue.
  - Also save overlapping pending and cancelled bookings at the same venue.
- **Expected result:** Every save succeeds.
- **Note:** This case passes before the rule exists. It is there to fail if the rule is drawn too widely, e.g. if touching periods were treated as overlapping.
- **Automated:** `test_database_rule_allows_what_is_not_a_conflict`

**TC-41-14 · An approval refused by the database rule is reported as a conflict**
- **Traces to:** AC3, AC6 · **Type:** Negative (concurrency) · **Depends on:** Q3
- **Preconditions:** E3's confirmed booking at Aurora, 18:00–20:00, is saved after P1's conflict check has run. This simulates a competing approval through a path that did not take the lock.
- **Steps:** As `gus`, approve P1.
- **Expected result:**
  - HTTP 409 with `reason: "conflict"`. `conflicts` lists E3's booking, and the message says the booking clashes.
  - P1 stays pending with no decision, and E1's venue is unchanged.
  - No notification is saved and no email is queued.
- **Automated:** `test_approval_refused_by_the_database_rule_is_a_conflict`

## AC7 — The check cannot be completed

**TC-41-15 · Approving: availability could not be verified**
- **Traces to:** AC7 · **Type:** Negative (failure)
- **Preconditions:** Reading the venue's blocks fails with a database error.
- **Steps:** As `gus`, approve P1. Then approve it again after the database recovers.
- **Expected result:**
  - The first call gives HTTP 503 with `retryable: true`. The error says availability could not be verified, so the booking was not approved.
  - P1 stays pending with no decision, E1's venue is unchanged, nobody is notified, and no email is queued.
  - The second call confirms P1.
- **Automated:** `test_unverified_availability_prevents_approval`

**TC-41-16 · The list: availability could not be verified**
- **Traces to:** AC7 · **Type:** Negative (failure) · **Depends on:** Q4
- **Preconditions:** Reading venue blocks fails with a database error.
- **Steps:** As `gus`, list the pending requests.
- **Expected result:** HTTP 503 with `retryable: true` and an error saying availability could not be verified. No `bookings` are returned, so no request is shown as having no conflicts.
- **Automated:** `test_list_reports_unverified_availability`

**TC-41-17 · Frontend: the message is shown and can be retried**
- **Traces to:** AC7 · **Type:** Negative (frontend, regression)
- **Expected result:**
  - The page shows the server's error, whether the list or an approval failed.
  - The list offers Retry, and the request stays listed so it can be approved again.
- **Automated:** already covered: TC-39-20's retry test ("shows a retryable error when the requests cannot be loaded") and TC-40-29 ("shows why approval failed …"). Both show the server's message as given.

## Reopened 26 Oct 2026 — unexpired tentative holds (AC1)

The customer added unexpired tentative holds to AC1. The other criteria are unchanged.

**The behaviour already exists.** SCRUM-87 added unexpired holds to the shared conflict check (`_conflicts_for` in `backend/app/venues/routes.py`). Approving, placing a hold, the pending list and the request-time check (SCRUM-84) all use it. Its tests already prove AC1–AC6 for holds:

| AC | For holds | Automated (SCRUM-87) |
|----|-----------|----------------------|
| AC1, AC2, AC3 | An overlapping unexpired hold refuses approving and holding (409, listed with its period, event and expiry), and nothing is confirmed. The pending list shows it among a request's conflicts. | TC-87-13, 14 · `test_unexpired_hold_blocks_approving_and_holding`, `test_pending_list_shows_a_hold_as_a_conflict` |
| AC2 (frontend) | The clash is shown as "Tentative hold for … until …, period". | TC-87-35 · "explains a refused hold …" |
| AC4 | Another venue's hold, and a hold that only touches, don't conflict. | TC-87-15 · `test_touching_and_other_venues_holds_do_not_block` |
| AC5 | An expired hold (expiry exactly now included) blocks nothing, so approval proceeds. | TC-87-16 · `test_expired_hold_blocks_nothing` |
| AC6 | Placing a hold locks the booking and venue rows, as approving does, so competing decisions at one venue happen one at a time. | TC-87-18 · `test_booking_and_venue_rows_are_locked_before_the_conflict_check`; TC-41-11 |

The only gap was **AC7 for holds**: no test made the holds part of the check fail. The following cases close it:

**TC-41-18 · Approving when the holds can't be read**
- **Traces to:** AC1, AC7 · **Type:** Negative (failure)
- **Preconditions:** Reading the venue's unexpired holds fails with a database error.
- **Steps:** As `gus`, approve P1. Then approve it again after the database recovers.
- **Expected result:**
  - The first call gives HTTP 503 with `retryable: true`, saying availability could not be verified.
  - P1 stays pending, and nothing is announced.
  - The second call confirms P1.
- **Automated:** `test_unreadable_holds_prevent_approval`

**TC-41-19 · The pending list when the holds can't be read**
- **Traces to:** AC1, AC7 · **Type:** Negative (failure)
- **Preconditions:** As TC-41-18.
- **Expected result:** HTTP 503 with `retryable: true`, saying availability could not be verified, and no `bookings`.
- **Automated:** `test_list_with_unreadable_holds_reports_unverified_availability`

These two passed the first time they ran, because the behaviour already existed (there was no red phase). A mutation check showed they can fail: with holds removed from the conflict check, both failed, as did TC-87-13 and 14.

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 02, 03, 04, 08, 18, 19; for holds TC-87-13, 14 |
| AC2 | 01, 02, 03, 06, 07, 08 |
| AC3 | 08, 14 |
| AC4 | 05, 09, 13 |
| AC5 | 01, 10, 13 |
| AC6 | 11, 12, 13, 14 |
| AC7 | 15, 16, 17, 18, 19 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 06, 07, 10 |
| Negative | 02, 03, 08, 12, 14, 15, 16, 17, 18, 19 |
| Boundary | 04, 05, 09, 13 |
| Concurrency | 11, 14 |
| Frontend | 06, 07, 17 |
| Regression (SCRUM-40 tests) | 08, 09, 10, 11, 17 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Is a conflict only an overlap with a confirmed booking or a block, plus the event already having a venue (assumed)? Should operating hours, capacity or "not currently bookable" also count? (SCRUM-40 Q2, Q3) | A1, A3, TC-41-03, 04 |
| Q2 | Should Approve stay available when the list shows conflicts (assumed: yes, because the server checks again), or be disabled? Should the list refresh after each approval (assumed)? | A2, A6, TC-41-06, 07 |
| Q3 | When blocks can be added (not built yet), should adding a block over a confirmed booking be refused, as two overlapping confirmed bookings are? | A4, TC-41-12, 13, 14 |
| Q4 | If conflicts cannot be checked, should the list still show the requests, each marked "availability not verified", instead of failing as a whole (assumed)? | A5, TC-41-16 |
| Q5 | Does a hold count as expired at its expiry time (assumed, as in SCRUM-87), or only after it? | A1, TC-41-18, 19; TC-87-16 |
