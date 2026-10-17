# SCRUM-87 — Venue Staff Place a Tentative Hold: Test Cases

**User story:** As Venue Staff, I want to approve a venue booking request as a tentative hold with an expiry date and time that I set, so that the coordinator can finalise the event without the venue being held indefinitely.

**Created:** 17 Oct 2026 · **Status of all cases:** Not yet run · **Automated tests:** `backend/tests/test_venue_holds.py`, `frontend/src/pages/VenueBookingRequestsPage.test.jsx`, `frontend/src/pages/TentativeHoldsPage.test.jsx`, `frontend/src/pages/VenueAvailabilityPage.test.jsx` · **Related:** Week 7 customer change 4 (tentative venue holds expire), SCRUM-40 (approving a request), SCRUM-41 (conflict checks), SCRUM-64 (calendar rules), SCRUM-37 (venue search)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | Venue Staff reviewing a Pending venue booking request can approve it as a tentative hold. The hold starts when Venue Staff approve it. |
| AC2 | Venue Staff must set the expiry date and time, which must be in the future. The system does not set a fixed duration. |
| AC3 | Venue Staff can change the expiry of a hold before it expires. |
| AC4 | An unexpired hold blocks the slot for conflict checks and shows as Tentative on the availability calendar. |
| AC5 | The coordinator is notified that the hold was placed, with its expiry. |
| AC6 | Only Venue Staff can place a hold or change its expiry. Anyone else is denied and nothing changes. |
| AC7 | If saving fails, no hold is created or changed and an error is shown. |

## Working assumptions

These are the team's current reading of the story, agreed with the scrum lead on 17 Oct 2026. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — A hold is a booking status:**
  - Placing a hold changes a pending request's status to `tentative` and records three things:
    - `held_at`: when the hold was placed (naive UTC). This is when the hold starts (AC1).
    - `held_by_id`: the Venue Staff member who placed it.
    - `hold_expires_at`: the expiry.
  - The event's venue and status are unchanged, because a hold is not a confirmed booking.
  - The request leaves the pending list.
- **A2 — The expiry (AC2):**
  - It is a date and time entered by Venue Staff, in Singapore time like the booking's own times.
  - It must be later than the current Singapore time, and no later than the booking's start. A hold can't outlast the time it holds. *(Q1)*
  - So a booking whose time has already started can't be held: no expiry can satisfy both rules, and the request is refused as an invalid expiry.
  - There is no default or maximum duration.
- **A3 — When a hold counts:** a hold is unexpired while its expiry is later than the current Singapore time. At the expiry itself it has expired. An unexpired hold:
  - **conflicts** with approving, or holding, another request whose period overlaps it at the same venue. It is listed with the other conflicts (SCRUM-41), with its event and expiry. Periods are half-open, so touching periods don't conflict.
  - **appears on the calendar** (SCRUM-64) as a "hold" period with its expiry. The time it covers is shown as **tentative**, or as unavailable when something else also makes it unavailable (e.g. outside operating hours).
  - **leaves the venue out of search** (SCRUM-37) for an overlapping time. *(Q2)*

  An expired hold does none of these.
- **A4 — The same checks as approving:**
  - Only a pending request can be held, and its event must still be approved (SCRUM-40 A4).
  - The request is refused if it clashes with a confirmed booking, a block, an unexpired hold, or a confirmed booking the event already has (SCRUM-40 A2/A3).
  - The booking and venue rows are locked while the decision is made (SCRUM-40 A7).
  - If conflicts can't be checked, nothing is held (SCRUM-41 A5).
- **A5 — Changing the expiry (AC3):**
  - Only an unexpired `tentative` booking's expiry can be changed. The new expiry follows A2.
  - The period and venue don't change, so no conflict check is needed.
  - The booking row is locked while it is changed.
- **A6 — Notifications (AC5):** the event's current coordinator gets an in-app notification, saved in the same commit, and an email queued afterwards:
  - when a hold is placed (kind `venue_hold_placed`), naming the venue, the period and the expiry;
  - when its expiry changes (kind `venue_hold_expiry_changed`), with the old and new expiry. *(Q3)*

  If the email can't be queued, the hold or change still stands, and the reply says so.
- **A7 — Order of checks (AGENTS.md, the venues module's role-first pattern):**
  1. not logged in (401);
  2. not Venue Staff (403);
  3. unknown booking (404);
  4. an invalid expiry (400, `field: "expires_at"`);
  5. the booking isn't in the right state (409);
  6. conflicts can't be checked (503);
  7. conflicts (409).
- **A8 — Where Venue Staff work:**
  - The pending list (SCRUM-39/40) gains an expiry field and "Place tentative hold" for each request.
  - A new **Tentative holds** page lists unexpired holds, soonest expiry first, and lets Venue Staff change each expiry.
- **A9 — Out of scope:**
  - **Confirming a hold:** SCRUM-40's Approve still accepts only pending requests, so a hold is refused there. Confirming one is a separate story.
  - **What happens when a hold expires,** including notifying the coordinator then (Week 7 change 4). Until that is built, an expired hold stays `tentative` but blocks nothing and isn't listed. *(Q4)*
  - **The coordinator's venue request page** doesn't show holds.

## Endpoints under test

- **`POST /api/venues/bookings/<id>/hold`** with `{"expires_at": "YYYY-MM-DDTHH:MM"}`:
  - **200** `{"message", "booking": hold, "notification": {"in_app": true, "email_queued": bool}}`.
  - **400** `{"error", "field": "expires_at"}`.
  - **409** `{"error", "reason": "not_pending" | "event_not_approved" | "conflict", "conflicts"?}`.
  - **503** `{"error", "retryable": true}`.
- **`PATCH /api/venues/bookings/<id>/hold`** with `{"expires_at": "YYYY-MM-DDTHH:MM"}`:
  - **200** `{"message", "booking": hold, "notification"}`.
  - **400** as above.
  - **409** `{"error", "reason": "not_a_hold" | "expired"}`.
  - **503** as above.
- **`GET /api/venues/holds`:** **200** `{"holds": [hold, ...], "message"}`. Only unexpired holds, soonest expiry first. **503** on failure.
- **All three:** **401** without a valid session, and **403** for anyone who isn't Venue Staff. The two `/hold` endpoints also return **404** for an unknown booking.
- **The `hold` payload** is SCRUM-39's booking payload (status `tentative`) plus `"hold": {"held_at", "held_by": {"id", "email"}, "expires_at"}`.
- **A hold conflict** (SCRUM-41 list, SCRUM-40/87 refusals) is `{"type": "hold", "id", "start", "end", "event": {"id", "title"} | null, "expires_at"}`.
- **On the calendar** (SCRUM-64), a hold period is `{"type": "hold", "id", "start", "end", "reason": null, "expires_at"}`. Slots gain:
  - the status `"tentative"`;
  - the cause `"hold"`, ordered `booking`, `block`, `hold`, `outside_operating_hours`.

## Seed data (VH-SEED)

SCRUM-40's VA-SEED, reset before **every** test case:
- **users:**
  - gus (Venue Staff);
  - alice and ben (coordinators);
  - dana (organiser);
  - hana (tech staff);
  - farah (attendee);
  - admin;
- **venues:** Aurora Ballroom (Mon–Sun 08:00–23:00) and Civic Hall (Mon–Fri 09:00–18:00);
- **approved events:**
  - E1 Harbour Lights Festival (alice);
  - E2 Winter Networking Night (ben);
  - E3 Product Launch (alice);
- **pending requests:**
  - P1: E1 at Aurora Ballroom, Fri 12 Mar 2027 16:00–22:30;
  - P2: E2 at Civic Hall, Sat 3 Apr 2027 17:00–21:30.

"Now" is fixed at **Mon 1 Mar 2027 12:00** (Singapore time) in every case, so the time boundaries are exact. The usual expiry is **Mon 1 Mar 2027 17:00**, and an expired hold expired on **Mon 1 Feb 2027 09:00**. The cases add any holds, bookings and blocks they need.

---

## AC1 — Placing a hold

**TC-87-01 · Venue Staff place a tentative hold on a pending request**
- **Traces to:** AC1, AC2 · **Type:** Happy path
- **Steps:** As `gus`, place a hold on P1 expiring 2027-03-01 17:00.
- **Expected result:**
  - HTTP 200.
  - P1 is `tentative`, held by gus, at a time between the request's start and end. Its expiry is exactly 2027-03-01 17:00.
  - E1's venue is still unset, and its status is still `approved`.
  - The reply's booking shows the same values. The message names Aurora Ballroom, the event and the expiry.
  - P1 is no longer in the pending list and is in the holds list.
- **Automated:** `test_venue_staff_place_a_tentative_hold`

**TC-87-02 · Only a pending request can be placed on hold**
- **Traces to:** AC1 · **Type:** Negative (business rule)
- **Steps:** Place a hold on a confirmed, a rejected, a cancelled and a tentative booking.
- **Expected result:** HTTP 409 `not_pending` each time, naming the status. Nothing changes.
- **Automated:** `test_only_a_pending_request_can_be_held`

**TC-87-03 · The event must still be approved**
- **Traces to:** AC1 · **Type:** Negative (business rule)
- **Preconditions:** E1 is cancelled while P1 is pending.
- **Expected result:** HTTP 409 `event_not_approved`. P1 stays pending.
- **Automated:** `test_event_must_still_be_approved`

**TC-87-04 · Unknown booking**
- **Traces to:** AC1 · **Type:** Negative
- **Expected result:** HTTP 404 "Booking request not found." for both placing a hold and changing an expiry.
- **Automated:** `test_unknown_booking_is_not_found`

## AC2 — The expiry

**TC-87-05 · The expiry is required, as a date and time, and nothing else may be sent**
- **Traces to:** AC2 · **Type:** Negative (validation)
- **Steps:** Place a hold on P1 with each of these:
  - no body;
  - `{}`;
  - an empty expiry;
  - a null expiry;
  - `"tomorrow"`;
  - `"2027-02-30T10:00"`;
  - `"2027-03-01"`;
  - a number;
  - a valid expiry plus another field.
- **Expected result:** HTTP 400 each time, with `field: "expires_at"` (except the extra field, which names the field). P1 stays pending, and nothing is announced.
- **Automated:** `test_expiry_must_be_a_date_and_time`

**TC-87-06 · The expiry must be in the future**
- **Traces to:** AC2 · **Type:** Boundary
- **Expected result:** (now is Mon 1 Mar 2027 12:00)
  - An expiry of 11:59 is refused (400), and so is exactly 12:00.
  - 12:01 is accepted.
- **Automated:** `test_expiry_must_be_in_the_future`

**TC-87-07 · The expiry must be no later than the booking's start**
- **Traces to:** AC2 · **Type:** Boundary · **Depends on:** Q1
- **Expected result:**
  - An expiry of 2027-03-12 16:01 (one minute after P1 starts) is refused (400), naming the start.
  - Exactly 16:00 is accepted.
  - A request whose time has already started (1 Jan 2020) can't be held: any expiry is refused (400).
- **Automated:** `test_expiry_must_be_no_later_than_the_start`

**TC-87-08 · There is no fixed duration**
- **Traces to:** AC2 · **Type:** Happy path
- **Steps:** Hold P1 until 2027-03-01 12:05 (five minutes from now), and P2 until 2027-04-03 17:00 (its start, a month away).
- **Expected result:** Each is stored exactly as entered, with no default or rounding.
- **Automated:** `test_any_valid_expiry_is_kept_as_entered`

## AC3 — Changing the expiry

**TC-87-09 · Venue Staff change an unexpired hold's expiry**
- **Traces to:** AC3 · **Type:** Happy path
- **Preconditions:** H1, a hold on P1 expiring 2027-03-01 17:00.
- **Steps:**
  1. As `gus`, change the expiry to 2027-03-05 12:00.
  2. Then change it to 2027-03-02 09:00.
- **Expected result:**
  - Both changes succeed (HTTP 200) and are saved.
  - The booking stays `tentative`, keeps its period, and keeps who held it and when.
  - The reply shows the new expiry.
- **Automated:** `test_venue_staff_change_a_holds_expiry`

**TC-87-10 · The new expiry follows the same rules**
- **Traces to:** AC2, AC3 · **Type:** Negative (validation)
- **Steps:** Change H1's expiry to a past time, to after P1's start, and to `"soon"`.
- **Expected result:** HTTP 400 `field: "expires_at"` each time. The expiry stays 2027-03-01 17:00, and nothing is announced.
- **Automated:** `test_new_expiry_follows_the_same_rules`

**TC-87-11 · Only a hold has an expiry to change**
- **Traces to:** AC3 · **Type:** Negative (business rule)
- **Steps:** Change the expiry of pending P2 and of a confirmed booking.
- **Expected result:** HTTP 409 `not_a_hold`. Nothing changes.
- **Automated:** `test_only_a_hold_has_an_expiry_to_change`

**TC-87-12 · An expired hold can't be changed**
- **Traces to:** AC3 · **Type:** Boundary · **Depends on:** Q4
- **Preconditions:** One hold expires exactly now (Mon 1 Mar 2027 12:00), and another one minute later.
- **Expected result:**
  - The hold expiring at 12:00 has expired: changing it gives HTTP 409 `expired`, naming its expiry, and nothing changes.
  - The hold expiring at 12:01 can still be changed.
- **Automated:** `test_an_expired_hold_cannot_be_changed`

## AC4 — An unexpired hold blocks the slot

**TC-87-13 · An unexpired hold blocks approving and holding an overlapping request**
- **Traces to:** AC4 · **Type:** Negative (conflict)
- **Preconditions:** H2, an unexpired hold for E3 at Aurora Ballroom, 12 Mar 2027 18:00–20:00, expiring 2027-03-01 17:00.
- **Steps:** Approve P1, then try to place a hold on it.
- **Expected result:**
  - Both are refused with HTTP 409 `conflict`, listing H2 (type `hold`, its times, E3 and the expiry).
  - P1 stays pending.
- **Automated:** `test_unexpired_hold_blocks_approving_and_holding`

**TC-87-14 · The pending list shows an unexpired hold as a conflict**
- **Traces to:** AC4 · **Type:** Negative (conflict)
- **Preconditions:** As TC-87-13.
- **Expected result:** P1's `conflicts` in the pending list is exactly H2's conflict entry.
- **Automated:** `test_pending_list_shows_a_hold_as_a_conflict`

**TC-87-15 · Touching holds and other venues' holds don't block**
- **Traces to:** AC4 · **Type:** Boundary
- **Preconditions:**
  - Unexpired holds at Aurora Ballroom ending at 16:00 and starting at 22:30 on 12 Mar 2027.
  - An unexpired hold at Civic Hall during P1.
- **Expected result:** P1 can be approved (HTTP 200).
- **Automated:** `test_touching_and_other_venues_holds_do_not_block`

**TC-87-16 · An expired hold blocks nothing**
- **Traces to:** AC4 · **Type:** Boundary · **Depends on:** Q4
- **Preconditions:** As TC-87-13, but H2 expires exactly now (2027-03-01 12:00).
- **Expected result:**
  - P1 has no conflicts in the pending list.
  - P1 can be approved.
- **Automated:** `test_expired_hold_blocks_nothing`

**TC-87-17 · Placing a hold is refused by the same conflicts as approving**
- **Traces to:** AC4 · **Type:** Negative (conflict)
- **Steps:** Place a hold on P1 when Aurora Ballroom has an overlapping confirmed booking, then an overlapping block. Then try again when E1 already has a confirmed venue.
- **Expected result:** HTTP 409 `conflict` each time, listing the clash. P1 stays pending.
- **Automated:** `test_placing_a_hold_checks_the_usual_conflicts`

**TC-87-18 · Holds on one venue are placed one at a time**
- **Traces to:** AC4 · **Type:** Concurrency
- **Expected result:** Placing a hold locks the booking's row and its venue's row before the conflict check reads anything (`SELECT … FOR UPDATE`).
- **Automated:** `test_booking_and_venue_rows_are_locked_before_the_conflict_check`

**TC-87-19 · No hold when conflicts can't be checked**
- **Traces to:** AC4, AC7 · **Type:** Negative (failure)
- **Preconditions:** Reading venue blocks fails with a database error.
- **Expected result:**
  - HTTP 503 with `retryable: true`, saying availability could not be verified. P1 stays pending.
  - A retry with the database working succeeds.
- **Automated:** `test_no_hold_when_conflicts_cannot_be_checked`

**TC-87-20 · The calendar shows an unexpired hold as Tentative**
- **Traces to:** AC4 · **Type:** Happy path
- **Preconditions:**
  - H2 (18:00–20:00 on 12 Mar 2027).
  - H3, an unexpired hold at Aurora Ballroom on Sat 13 Mar 2027, 22:00–23:30.
- **Steps:** As `alice`, view Aurora Ballroom for 12–13 Mar 2027.
- **Expected result:**
  - **Listed periods:** H2 and H3, as type `hold` with their expiry. Pending P1 isn't listed.
  - **Slots on 12 Mar:**
    - 08:00–18:00 available;
    - 18:00–20:00 tentative (hold);
    - 20:00–23:00 available.
  - **Slots on 13 Mar:**
    - 22:00–23:00 tentative (hold);
    - 23:00–23:30 unavailable (hold, outside operating hours);
    - 23:30–24:00 unavailable (outside operating hours).
- **Automated:** `test_calendar_shows_an_unexpired_hold_as_tentative`

**TC-87-21 · The calendar ignores an expired hold**
- **Traces to:** AC4 · **Type:** Boundary · **Depends on:** Q4
- **Preconditions:** H2, but expired (expiry 2027-02-01 09:00).
- **Expected result:** H2 isn't listed, and 18:00–20:00 on 12 Mar is available.
- **Automated:** `test_calendar_ignores_an_expired_hold`

**TC-87-22 · Venue search leaves out a venue held for the searched time**
- **Traces to:** AC4 · **Type:** Negative · **Depends on:** Q2
- **Steps:** As `alice`, search for 12 Mar 2027 18:00–20:00, with H2 unexpired and then expired.
- **Expected result:** Aurora Ballroom isn't found while H2 is unexpired, and is found once it has expired.
- **Automated:** `test_search_leaves_out_a_venue_held_for_the_time`

## AC5 — The coordinator is notified

**TC-87-23 · The coordinator is notified that the hold was placed, with its expiry**
- **Traces to:** AC5 · **Type:** Happy path
- **Steps:** Place the hold from TC-87-01.
- **Expected result:**
  - alice (E1's coordinator) has one `venue_hold_placed` notification for E1. It names Aurora Ballroom, the period (2027-03-12 16:00 to 22:30) and the expiry (2027-03-01 17:00).
  - One email to alice is queued with the same details.
  - Nobody else is notified.
  - The reply has `notification: {"in_app": true, "email_queued": true}`.
- **Automated:** `test_coordinator_is_notified_of_the_hold_and_its_expiry`

**TC-87-24 · The coordinator is notified when the expiry changes**
- **Traces to:** AC3, AC5 · **Type:** Happy path · **Depends on:** Q3
- **Steps:** Change H1's expiry to 2027-03-05 12:00.
- **Expected result:** alice gets one `venue_hold_expiry_changed` notification and one email, both naming the old expiry (2027-03-01 17:00) and the new one.
- **Automated:** `test_coordinator_is_notified_when_the_expiry_changes`

**TC-87-25 · The hold stands when the email can't be queued**
- **Traces to:** AC5 · **Type:** Negative (failure)
- **Expected result:** Placing a hold and changing an expiry both succeed with `email_queued: false`. The hold or change, and its in-app notification, are saved.
- **Automated:** `test_hold_stands_when_the_email_cannot_be_queued`

## AC6 — Only Venue Staff

**TC-87-26 · Only Venue Staff can place a hold**
- **Traces to:** AC6 · **Type:** Negative (authorisation)
- **Steps:** Place a hold on P1 as alice, dana, hana, farah and admin.
- **Expected result:** HTTP 403 for each. P1 stays pending, and nobody is notified.
- **Automated:** `test_only_venue_staff_can_place_a_hold`

**TC-87-27 · Only Venue Staff can change a hold's expiry**
- **Traces to:** AC6 · **Type:** Negative (authorisation)
- **Steps:** Change H1's expiry as the same users, and list the holds as them.
- **Expected result:** HTTP 403 for each. The expiry is unchanged, and no hold data is returned.
- **Automated:** `test_only_venue_staff_can_change_or_list_holds`

**TC-87-28 · A valid session is required**
- **Traces to:** AC6 · **Type:** Negative (authentication)
- **Steps:** Use no token, an expired token, and a token for a deleted user.
- **Expected result:** HTTP 401 for placing, changing and listing. Nothing changes.
- **Automated:** `test_a_valid_session_is_required`

## AC7 — A failed save changes nothing

**TC-87-29 · Placing a hold fails to save**
- **Traces to:** AC7 · **Type:** Negative (failure)
- **Preconditions:** The commit raises `SQLAlchemyError`.
- **Expected result:**
  - HTTP 503 with `retryable: true`, saying the hold was not saved.
  - P1 stays pending, with no hold details, no notification and no email.
  - A retry with the database working succeeds.
- **Automated:** `test_failed_hold_save_changes_nothing`

**TC-87-30 · Changing an expiry fails to save**
- **Traces to:** AC7 · **Type:** Negative (failure)
- **Expected result:** HTTP 503 with `retryable: true`, saying the new expiry was not saved. The expiry stays 2027-03-01 17:00, with no notification and no email.
- **Automated:** `test_failed_expiry_change_changes_nothing`

## The holds list (A8)

**TC-87-31 · Venue Staff see the unexpired holds, soonest expiry first**
- **Traces to:** AC3 · **Type:** Happy path
- **Preconditions:**
  - H1 (expiring 2027-03-01 17:00);
  - H4 (expiring 2027-03-01 13:00);
  - an expired hold (2027-02-01 09:00).
- **Expected result:**
  - H4 is listed, then H1, each with its hold details. The expired hold isn't listed.
  - With no unexpired holds, the list is empty and has a message.
- **Automated:** `test_venue_staff_see_unexpired_holds_soonest_expiry_first`

**TC-87-32 · The holds list fails to load**
- **Traces to:** AC3, AC7 · **Type:** Negative (failure)
- **Expected result:** HTTP 503 with `retryable: true` and no `holds`.
- **Automated:** `test_holds_list_failure_is_reported`

**TC-87-33 · Approving a hold is still refused (confirming is a separate story)**
- **Traces to:** AC1 · **Type:** Negative (regression) · **Depends on:** Q4
- **Expected result:** SCRUM-40's Approve on H1 gives HTTP 409 `not_pending`, naming `tentative`. Nothing changes.
- **Automated:** `test_approving_a_hold_is_refused`

## Frontend

**TC-87-34 · Pending list: place a hold with an expiry**
- **Traces to:** AC1, AC2 · **Type:** Happy path (frontend)
- **Steps:** Enter an expiry for P1 and press "Place tentative hold".
- **Expected result:**
  - `{expires_at}` is sent to `POST /venues/bookings/<id>/hold`.
  - The server's confirmation is shown.
  - P1 leaves the list, and the list is reloaded.
- **Automated:** "places a tentative hold with the expiry entered" (`VenueBookingRequestsPage.test.jsx`)

**TC-87-35 · Pending list: a refused hold is explained and nothing is lost**
- **Traces to:** AC2, AC4, AC7 · **Type:** Negative (frontend)
- **Steps:** The server refuses with 400 (expiry), 409 (a clash with a hold) or 503, or the network fails.
- **Expected result:**
  - The message is shown. A clash with a hold is listed as "Tentative hold for Product Launch until 2027-03-01 17:00, 2027-03-12 18:00 to 2027-03-12 20:00".
  - P1 stays, with the entered expiry kept.
- **Automated:** "explains a refused hold and keeps the request and expiry" (`VenueBookingRequestsPage.test.jsx`)

**TC-87-36 · Holds page: the unexpired holds**
- **Traces to:** AC3 · **Type:** Happy path (frontend)
- **Expected result:**
  - **Each hold** shows its event, venue, period, "Expires: 2027-03-01 17:00" and who held it.
  - **An empty list** shows the server's message.
  - **A load failure** shows the error with Retry.
  - **A 403** shows its message with no Retry.
- **Automated:** `TentativeHoldsPage.test.jsx`

**TC-87-37 · Holds page: change an expiry**
- **Traces to:** AC3, AC7 · **Type:** Happy path / negative (frontend)
- **Expected result:**
  - Entering a new expiry and pressing "Change expiry" sends `{expires_at}` to `PATCH /venues/bookings/<id>/hold`. It then shows the server's confirmation and reloads the list.
  - On failure, the message is shown and the hold and entered expiry stay.
- **Automated:** `TentativeHoldsPage.test.jsx`

**TC-87-38 · Calendar: a hold is shown as Tentative**
- **Traces to:** AC4 · **Type:** Happy path (frontend)
- **Expected result:**
  - The slot reads "18:00–20:00 Tentative — on hold".
  - The period reads "Tentative hold: Fri 12 Mar 2027, 18:00 to Fri 12 Mar 2027, 20:00 (expires Mon 1 Mar 2027, 17:00)".
- **Automated:** "shows a tentative hold" (`VenueAvailabilityPage.test.jsx`)

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 03, 04, 33, 34 |
| AC2 | 01, 05, 06, 07, 08, 10, 34, 35 |
| AC3 | 09, 10, 11, 12, 24, 31, 32, 36, 37 |
| AC4 | 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 35, 38 |
| AC5 | 23, 24, 25 |
| AC6 | 26, 27, 28 |
| AC7 | 19, 29, 30, 32, 35, 37 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 08, 09, 20, 23, 24, 31, 34, 36, 37, 38 |
| Negative | 02, 03, 04, 05, 10, 11, 13, 14, 17, 19, 22, 25, 26, 27, 28, 29, 30, 32, 33, 35, 37 |
| Boundary | 06, 07, 12, 15, 16, 21 |
| Concurrency | 18 |
| Frontend | 34, 35, 36, 37, 38 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Can a hold's expiry be later than the booking's start? Assumed not: a hold can't outlast the time it holds. | A2, TC-87-07, 10 |
| Q2 | Should venue search leave out a venue that is held for the searched time (assumed), or still list it? | A3, TC-87-22 |
| Q3 | Should the coordinator be told when Venue Staff change a hold's expiry (assumed), or only when it is placed? | A6, TC-87-24 |
| Q4 | What happens when a hold expires: is the coordinator warned beforehand, and does the request go back to pending or close? How is a hold confirmed? (Week 7 change 4; separate stories.) Until then, an expired hold blocks nothing and can't be changed. | A9, TC-87-12, 16, 21, 33 |
