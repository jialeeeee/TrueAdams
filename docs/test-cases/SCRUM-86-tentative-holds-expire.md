# SCRUM-86 — Tentative Venue Holds Expire: Test Cases

**User story:** As an Event Coordinator, I want to confirm a tentative hold before it expires, or be told when it expires, so that venues are not blocked by plans that never get confirmed.

**Created:** 29 Oct 2026 · **Status of all cases:** Automated cases pass (29 Oct 2026, local PostgreSQL built from the models, with db/venue_hold_expiry.sql's column + Vitest); frontend cases 32–34 also to be checked manually in the browser, and the beat schedule with `docker compose up` · **Automated tests:** `backend/tests/test_venue_hold_expiry.py`, `frontend/src/pages/VenueBookingRequestPage.test.jsx` · **Related:** Week 7 customer change 4 (tentative venue holds expire), SCRUM-87 (placing a hold), SCRUM-40 (approving a request), SCRUM-41 (conflict checks), SCRUM-85 (several venues for one event), SCRUM-94 (cancelling a booking), SCRUM-64 (calendar rules)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | Before the hold expires, the coordinator can confirm the held booking, which then becomes a confirmed booking. |
| AC2 | After the expiry date and time, the hold no longer blocks the slot, the calendar shows it as available, and the hold's status is Expired. An expired hold is never treated as a confirmed booking. |
| AC3 | The coordinator is notified 24 hours before the hold expires and again when it expires. |
| AC4 | An expired hold cannot be confirmed. The coordinator must submit a new booking request. |
| AC5 | Only the event's coordinator can confirm a hold. Anyone else is denied and nothing changes. |
| AC6 | If confirming fails to save, the hold stays Tentative and an error is shown. |
| AC7 | Times are in SGT. |

## Working assumptions

These are the team's current reading of the story, agreed with the scrum lead on 29 Oct 2026. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Confirming (AC1):**
  - The hold's status changes from `tentative` to `confirmed`. `decided_at` (naive UTC) and `decided_by_id` record the coordinator who confirmed it, as they record whoever confirmed any booking (SCRUM-40).
  - `held_at`, `held_by_id` and `hold_expires_at` are kept, as the hold's history.
  - It is then a confirmed booking everywhere: it blocks its occupied period, it appears on the calendar as a booking, and it leaves the holds list.
  - If it is the event's first confirmed booking, its venue becomes the event's venue (SCRUM-85 A4).
- **A2 — The same checks as approving:**
  - The event must still be approved (SCRUM-40 A4).
  - Conflicts are checked again with the booking and venue rows locked (SCRUM-40 A7). Something may have been recorded over the hold since it was placed, such as a block. The hold itself is never a conflict. *(Q1)*
  - If conflicts can't be checked, or the save fails for any reason, nothing is confirmed and the hold stays tentative (SCRUM-41 A5, AC6).
- **A3 — Expired (AC2, AC4):**
  - A hold has expired from its expiry itself, by Singapore time (SCRUM-87 A3).
  - From that moment its status is shown as `expired`, even before the expiry check has recorded it.
  - The expiry check records the status `expired` within 5 minutes (A4).
  - An expired hold blocks nothing, isn't listed as a hold, and can't be confirmed, approved or have its expiry changed.
  - On the coordinator's page it reads "Hold expired on …" and offers neither Confirm nor Cancel: nothing is held, so there is nothing to cancel. *(Q6)*
- **A4 — The expiry check (AC3):** a background job (Celery beat) runs every **5 minutes** (`HOLD_CHECK_INTERVAL_SECONDS`, scrum lead, 29 Oct 2026). Each run:
  - **records** each tentative hold whose expiry has passed as `expired` and tells the event's coordinator once (kind `venue_hold_expired`), naming the venue, the period and the expiry, and that a new venue request is needed;
  - **warns** the coordinator once (kind `venue_hold_expiring`) about each other tentative hold that expires within the next 24 hours, at most 24 hours before its expiry (`hold_warned_at` records it);
  - saves each notification with its change in one commit, and queues the emails afterwards. If an email can't be queued, the rest still go. If the run fails, nothing changes and the next run tries again.

  So each notice arrives within 5 minutes of its moment. *(Q2)*
  - **Short holds:** a hold placed, or changed, with an expiry within 24 hours gets no separate warning. The "hold placed" or "expiry changed" notice already gives the expiry (scrum lead, 29 Oct 2026). Changing the expiry to more than 24 hours away makes the warning due again. *(Q3)*
  - **A missed warning:** a hold found already expired gets only the expiry notice.
  - **Holds that expired before this is released** are recorded and notified on the first run. *(Q5)*
  - **No coordinator:** a hold whose event has no coordinator is still recorded as expired. There is just nobody to tell.
- **A5 — Venue Staff are told of a confirmation (scrum lead, 29 Oct 2026):** every Venue Staff member gets an in-app notification (kind `venue_hold_confirmed`) in the same commit, and an email afterwards. Venue Staff aren't linked to venues, as in SCRUM-94 A4. They aren't told when a hold expires. *(Q4)*
- **A6 — Order of checks (AGENTS.md; SCRUM-94's order for the coordinator):**
  1. not logged in (401);
  2. unknown booking (404);
  3. not the event's current coordinator (403);
  4. not a hold (409, `not_a_hold`);
  5. expired (409, `expired`);
  6. the event isn't approved (409, `event_not_approved`);
  7. conflicts can't be checked (503);
  8. conflicts (409, `conflict`).
- **A7 — SGT (AC7):** expiries are compared with the current Singapore time, never the server's or UTC. Messages give times as recorded, marked "(Singapore time)".
- **A8 — Where the coordinator works:** their venue request page lists the event's venue bookings (SCRUM-69/94, with the hold's expiry since SCRUM-87 A10). An unexpired hold there gains **Confirm booking**.
- **A9 — Out of scope:**
  - a screen listing in-app notifications (a separate story);
  - reopening or extending an expired hold.

## Endpoints under test

- **`POST /api/venues/bookings/<id>/confirm`** (no body):
  - **200** `{"message", "booking", "notification": {"in_app": true, "email_queued": bool}}`. `booking` is the coordinator's booking payload (SCRUM-69), now with status `confirmed` and `hold: null`.
  - **401** without a valid session.
  - **404** for an unknown booking.
  - **403** for anyone but the event's current coordinator.
  - **409** `{"error", "reason": "not_a_hold" | "expired" | "event_not_approved" | "conflict", "conflicts"?}`.
  - **503** `{"error", "retryable": true}`.
- **`GET /api/venues/bookings?event_id=<id>`** (SCRUM-69): an expired hold has status `expired` and `hold: {"expires_at", "expired": true}`.
- **The Celery task `tasks.check_hold_expiries`**, scheduled every 300 seconds by Celery beat (`check-hold-expiries`).
- **Model:** `VenueBooking.hold_warned_at` (naive UTC), from `db/venue_hold_expiry.sql`, and the status `expired`.

## Seed data (HE-SEED)

SCRUM-87's VH-SEED (SCRUM-40's VA-SEED), reset before **every** test case:
- **users:**
  - gus (Venue Staff);
  - alice and ben (coordinators);
  - dana (organiser);
  - hana (tech staff);
  - farah (attendee);
  - admin.
- **venues:** Aurora Ballroom and Civic Hall.
- **approved events:**
  - E1 Harbour Lights Festival (alice);
  - E2 Winter Networking Night (ben);
  - E3 Product Launch (alice).
- **pending requests:**
  - P1: E1 at Aurora Ballroom, Fri 12 Mar 2027 16:00–22:30;
  - P2: E2 at Civic Hall, Sat 3 Apr 2027 17:00–21:30.

**H1** is P1 held by gus, expiring **Mon 1 Mar 2027 17:00**.

"Now" is fixed at **Mon 1 Mar 2027 12:00** (Singapore time), except in TC-86-31. Cases change H1's expiry, or add holds, bookings and blocks, as they need.

---

## AC1 — Confirming a hold

**TC-86-01 · The coordinator confirms an unexpired hold**
- **Traces to:** AC1 · **Type:** Happy path
- **Steps:** As `alice`, confirm H1.
- **Expected result:**
  - HTTP 200. The reply's `booking` has status `confirmed` and `hold: null`, and its `message` names Aurora Ballroom and Harbour Lights Festival.
  - P1 is stored as `confirmed`, decided by alice (`decided_at` set). `held_at`, `held_by_id` and `hold_expires_at` are unchanged.
  - E1's venue is Aurora Ballroom.
- **Automated:** `test_coordinator_confirms_an_unexpired_hold`

**TC-86-02 · A confirmed hold is a confirmed booking**
- **Traces to:** AC1 · **Type:** Happy path
- **Steps:** Confirm H1. Then, as `gus`, list the holds, and approve P3, a pending E3 request at Aurora Ballroom for 12 Mar 2027 18:00–20:00.
- **Expected result:** H1 isn't among the holds. P3 is refused as a conflict with P1, listed as a `booking`.
- **Automated:** `test_confirmed_hold_is_a_confirmed_booking`

**TC-86-03 · The event's main venue stays**
- **Traces to:** AC1 · **Type:** Boundary (SCRUM-85 A4)
- **Preconditions:** E1 already has a confirmed booking at Civic Hall (13 Mar 2027 10:00–12:00), which is E1's venue.
- **Steps:** As `alice`, confirm H1.
- **Expected result:** HTTP 200, and E1's venue is still Civic Hall.
- **Automated:** `test_events_main_venue_is_kept`

**TC-86-04 · Venue Staff are told the hold was confirmed**
- **Traces to:** AC1 · **Type:** Happy path · **Depends on:** Q4
- **Preconditions:** A second Venue Staff member, vera.
- **Steps:** As `alice`, confirm H1.
- **Expected result:**
  - gus and vera each get one `venue_hold_confirmed` notification for E1. It names alice, Aurora Ballroom, Harbour Lights Festival and the period (2027-03-12 16:00 to 22:30).
  - One email to each of them is queued.
  - alice gets no notification.
  - The reply has `notification: {"in_app": true, "email_queued": true}`.
- **Automated:** `test_venue_staff_are_told_the_hold_was_confirmed`

**TC-86-05 · The confirmation stands when the email can't be queued**
- **Traces to:** AC1 · **Type:** Negative (failure)
- **Expected result:** HTTP 200 with `email_queued: false`. P1 is confirmed, and gus's notification is saved.
- **Automated:** `test_confirmation_stands_when_the_email_cannot_be_queued`

**TC-86-06 · Conflicts are checked again**
- **Traces to:** AC1 · **Type:** Negative · **Depends on:** Q1
- **Preconditions:** A block ("Electrical works") at Aurora Ballroom, 12 Mar 2027 18:00–20:00, recorded after H1 was placed.
- **Steps:** As `alice`, confirm H1.
- **Expected result:** HTTP 409, `reason: "conflict"`. The conflicts list the block and not H1 itself. P1 stays tentative.
- **Automated:** `test_confirming_rechecks_conflicts`

**TC-86-07 · Only a hold can be confirmed**
- **Traces to:** AC1 · **Type:** Negative
- **Steps:** As `alice`, confirm E1 bookings that are pending (P1, not held), confirmed, rejected and cancelled.
- **Expected result:** Each gives HTTP 409, `reason: "not_a_hold"`, and is unchanged.
- **Automated:** `test_only_a_hold_can_be_confirmed`

**TC-86-08 · The event must still be approved**
- **Traces to:** AC1 · **Type:** Negative · **Depends on:** Q1
- **Preconditions:** E1 is cancelled.
- **Expected result:** HTTP 409, `reason: "event_not_approved"`. P1 stays tentative.
- **Automated:** `test_event_must_still_be_approved`

**TC-86-09 · Unknown booking**
- **Traces to:** AC1 · **Type:** Negative
- **Expected result:** HTTP 404.
- **Automated:** `test_unknown_booking_is_not_found`

**TC-86-10 · The booking and venue are locked before the conflict check**
- **Traces to:** AC1 · **Type:** Concurrency (A2)
- **Expected result:** The booking row and the venue row are both read `FOR UPDATE` before the blocks are read. A competing approval, placement or expiry check at that venue therefore waits.
- **Automated:** `test_booking_and_venue_rows_are_locked_before_the_conflict_check`

## AC2 — After the expiry

**TC-86-11 · At its expiry the hold is Expired, before the check runs**
- **Traces to:** AC2 · **Type:** Boundary
- **Preconditions:** H1 expires at 2027-03-01 12:00, exactly now. The expiry check hasn't run.
- **Steps:** As `alice`, list E1's venue bookings. As `gus`, list the holds. Run the expiry check, then list both again.
- **Expected result:** Both times:
  - P1 has status `expired` and `hold: {"expires_at": "2027-03-01T12:00:00", "expired": true}`.
  - H1 isn't among the holds.
  - (The calendar already shows an expired hold's time as available: TC-87-21.)
- **Automated:** `test_hold_is_expired_from_its_expiry`

**TC-86-12 · The expiry check records expired holds**
- **Traces to:** AC2 · **Type:** Boundary
- **Preconditions:**
  - H1 expires at 12:00 (now).
  - H2, a hold for E3 at Aurora Ballroom (12 Mar 18:00–20:00), expired on 1 Feb 2027 09:00.
  - H3, a hold for E2 at Civic Hall (3 Apr 17:00–21:30), expires at 12:01.
- **Steps:** Run the expiry check.
- **Expected result:** H1 and H2 are stored as `expired`. H3 is still `tentative`.
- **Automated:** `test_expiry_check_records_expired_holds`

**TC-86-13 · An expired hold is never treated as a confirmed booking**
- **Traces to:** AC2 · **Type:** Negative
- **Preconditions:** H1 has expired, and the check has recorded it.
- **Steps:** As `gus`, approve P3 (E3 at Aurora Ballroom, 12 Mar 18:00–20:00).
- **Expected result:** P3 is confirmed. E1 still has no venue.
- **Automated:** `test_expired_hold_is_never_a_confirmed_booking`

**TC-86-14 · A recorded Expired hold's expiry can't be changed**
- **Traces to:** AC2 · **Type:** Negative (SCRUM-87 AC3)
- **Steps:** As `gus`, change the expiry of H1, which is recorded as expired.
- **Expected result:** HTTP 409, `reason: "expired"`, and nothing changes.
- **Automated:** `test_recorded_expired_hold_cannot_be_changed`

**TC-86-15 · The check leaves confirmed bookings alone**
- **Traces to:** AC2 · **Type:** Negative
- **Preconditions:** H1 was confirmed, and its old expiry (17:00 yesterday) has passed.
- **Steps:** Run the expiry check.
- **Expected result:** P1 is still `confirmed`, and nobody is notified.
- **Automated:** `test_expiry_check_leaves_confirmed_bookings_alone`

## AC3 — The coordinator is notified

**TC-86-16 · The coordinator is warned 24 hours before**
- **Traces to:** AC3 · **Type:** Boundary
- **Preconditions:**
  - H1 expires at 2027-03-02 12:00, exactly 24 hours from now.
  - H3 (E2, ben) expires at 2027-03-02 12:01.
- **Steps:** Run the expiry check.
- **Expected result:**
  - alice gets one `venue_hold_expiring` notification for E1. It names Aurora Ballroom, the period and the expiry (2027-03-02 12:00), and asks her to confirm before then.
  - One email to alice is queued with the same details.
  - H1's `hold_warned_at` is set.
  - ben gets nothing, and H3's `hold_warned_at` is still empty.
- **Automated:** `test_coordinator_is_warned_24_hours_before`

**TC-86-17 · The warning is sent once**
- **Traces to:** AC3 · **Type:** Negative
- **Steps:** As TC-86-16, running the check twice.
- **Expected result:** One notification and one email.
- **Automated:** `test_warning_is_sent_once`

**TC-86-18 · The coordinator is told when the hold expires**
- **Traces to:** AC3, AC4 · **Type:** Happy path
- **Preconditions:** H1 expires at 12:00 (now) and was warned earlier.
- **Steps:** Run the expiry check twice.
- **Expected result:**
  - alice gets one `venue_hold_expired` notification for E1. It names Aurora Ballroom, the period and the expiry, and says to submit a new venue request.
  - One email with the same details.
  - Nothing more on the second run.
- **Automated:** `test_coordinator_is_told_when_the_hold_expires`

**TC-86-19 · No separate warning for a hold placed with less than 24 hours left**
- **Traces to:** AC3 · **Type:** Boundary · **Depends on:** Q3
- **Steps:** As `gus`, place a hold on P1 expiring at 2027-03-01 17:00. Run the expiry check.
- **Expected result:** alice has only the `venue_hold_placed` notification, and only its email was queued.
- **Automated:** `test_no_separate_warning_for_a_hold_placed_with_under_24_hours`

**TC-86-20 · Changing the expiry makes the warning due again, or not**
- **Traces to:** AC3 · **Type:** Boundary · **Depends on:** Q3
- **Steps:**
  1. H1 has been warned. As `gus`, change its expiry to 2027-03-05 12:00 and run the check.
  2. Run the check again at 2027-03-04 12:00.
  3. As `gus`, change the expiry to 2027-03-04 18:00 and run the check.
- **Expected result:**
  1. No warning: `hold_warned_at` was cleared, and the new expiry is more than 24 hours away.
  2. One warning, naming 2027-03-05 12:00.
  3. No further warning. The "expiry changed" notice gives the new expiry, within 24 hours.
- **Automated:** `test_changing_the_expiry_rearms_the_warning`

**TC-86-21 · A hold found already expired gets only the expiry notice**
- **Traces to:** AC3 · **Type:** Boundary
- **Preconditions:** H1 expired on 1 Feb 2027 09:00 and was never warned.
- **Steps:** Run the expiry check.
- **Expected result:** alice gets only the `venue_hold_expired` notification.
- **Automated:** `test_expired_hold_gets_only_the_expiry_notice`

**TC-86-22 · The check carries on when an email can't be queued**
- **Traces to:** AC3 · **Type:** Negative (failure)
- **Preconditions:** H1 expires now. H3 (E2, ben) expires at 2027-03-02 10:00. Queuing emails fails.
- **Steps:** Run the expiry check.
- **Expected result:** H1 is recorded as expired and H3 as warned. alice and ben each have their in-app notification.
- **Automated:** `test_check_carries_on_when_an_email_cannot_be_queued`

**TC-86-23 · A failed check changes nothing**
- **Traces to:** AC3 · **Type:** Negative (failure)
- **Preconditions:** H1 expires now. Saving fails.
- **Steps:** Run the expiry check, then run it again after the database recovers.
- **Expected result:**
  - The first run leaves H1 `tentative`, with no notification and no email.
  - The second run records H1 as expired and tells alice.
- **Automated:** `test_failed_check_changes_nothing`

**TC-86-24 · A hold with nobody to tell still expires**
- **Traces to:** AC2, AC3 · **Type:** Boundary
- **Preconditions:** A hold at Aurora Ballroom with no event, expiring now.
- **Steps:** Run the expiry check.
- **Expected result:** It is recorded as expired, and no notification or email is made.
- **Automated:** `test_hold_without_a_coordinator_still_expires`

**TC-86-25 · The check runs every 5 minutes**
- **Traces to:** AC3 · **Type:** Configuration · **Depends on:** Q2
- **Expected result:** Celery beat's schedule has `check-hold-expiries`, running the registered task `tasks.check_hold_expiries` every 300 seconds.
- **Automated:** `test_check_runs_every_five_minutes`

## AC4 — An expired hold can't be confirmed

**TC-86-26 · Confirming an expired hold is refused**
- **Traces to:** AC4 · **Type:** Negative (boundary)
- **Steps:** As `alice`, confirm H1:
  - when it expires at 12:00 (now) and the check hasn't run;
  - after the check has recorded it as expired.
- **Expected result:**
  - Both give HTTP 409, `reason: "expired"`.
  - The error names the expiry (2027-03-01 12:00) and says to submit a new venue request.
  - P1 isn't confirmed, E1 has no venue, and nobody is notified.
- **Automated:** `test_expired_hold_cannot_be_confirmed`

## AC5 — Only the event's coordinator

**TC-86-27 · Anyone else is denied**
- **Traces to:** AC5 · **Type:** Negative (authorisation)
- **Steps:** Confirm H1 as ben (another coordinator), gus, dana, hana, farah, admin and a Coordinator Lead.
- **Expected result:** Each gets HTTP 403. P1 stays tentative, and nobody is notified.
- **Automated:** `test_only_the_events_coordinator_can_confirm`

**TC-86-28 · A valid session is required**
- **Traces to:** AC5 · **Type:** Negative (authorisation)
- **Steps:** Confirm H1 without a token, and with a token for a user that doesn't exist.
- **Expected result:** HTTP 401 both times, and P1 stays tentative.
- **Automated:** `test_a_valid_session_is_required`

## AC6 — A failed confirmation changes nothing

**TC-86-29 · Saving the confirmation fails**
- **Traces to:** AC6 · **Type:** Negative (failure)
- **Steps:** As `alice`, confirm H1 while saving fails. Then try again.
- **Expected result:**
  - HTTP 503 with `retryable: true`. The error says the hold is still tentative.
  - P1 stays tentative, E1 has no venue, and nobody is notified.
  - The second attempt confirms it.
- **Automated:** `test_failed_confirmation_changes_nothing`

**TC-86-30 · Conflicts can't be checked**
- **Traces to:** AC6 · **Type:** Negative (failure)
- **Preconditions:** Reading the venue's blocks fails.
- **Expected result:** HTTP 503 with `retryable: true`. The error says availability could not be verified and the hold is still tentative. P1 stays tentative.
- **Automated:** `test_no_confirmation_when_conflicts_cannot_be_checked`

## AC7 — Times are in SGT

**TC-86-31 · Expiry is judged by Singapore time**
- **Traces to:** AC7 · **Type:** Boundary
- **Preconditions:**
  - The clock reads 2027-03-01 04:30 UTC, which is 12:30 in Singapore. Nothing else fixes "now".
  - H1 expires at 2027-03-01 12:00, Singapore time.
  - H3 (E2) expires at 2027-03-01 13:00, Singapore time.
- **Steps:** As `alice`, confirm H1. Then run the expiry check.
- **Expected result:**
  - The confirmation is refused as expired. Measured in UTC, H1 would still have 7½ hours to go.
  - The check records H1 as expired and leaves H3 tentative.
  - alice's notice gives the expiry as 2027-03-01 12:00 (Singapore time).
- **Automated:** `test_expiry_is_judged_by_singapore_time`

## Frontend

**TC-86-32 · The coordinator confirms an unexpired hold**
- **Traces to:** AC1 · **Type:** Frontend
- **Steps:** On E1's venue request page, choose **Confirm booking** for the Aurora Ballroom hold.
- **Expected result:**
  - `POST /venues/bookings/11/confirm` is sent once.
  - The server's message is shown.
  - The list is read again and shows the booking as Confirmed, without Confirm booking.
- **Automated:** "confirms an unexpired hold" (`VenueBookingRequestPage.test.jsx`)

**TC-86-33 · Confirm booking is offered only for an unexpired hold**
- **Traces to:** AC2, AC4 · **Type:** Frontend
- **Preconditions:** The list has an unexpired hold, an expired hold (status `expired`), and pending, confirmed and cancelled bookings.
- **Expected result:**
  - Only the unexpired hold has **Confirm booking**.
  - The expired hold reads "Hold expired on 2027-03-01 12:00" and has no Cancel booking.
- **Automated:** "offers Confirm booking only for an unexpired hold" (`VenueBookingRequestPage.test.jsx`)

**TC-86-34 · A refused or failed confirmation is explained**
- **Traces to:** AC4, AC6 · **Type:** Frontend
- **Steps:** Confirm the hold:
  1. when the server refuses it as expired (409);
  2. when saving fails (503).
- **Expected result:**
  1. The server's error is shown. The list is read again, so the hold now reads "Hold expired on …", without Confirm booking.
  2. The server's error is shown. The hold is still listed as a tentative hold, and choosing Confirm booking again confirms it.
- **Automated:** "explains a refused confirmation and shows the hold as it now is" and "keeps the hold when saving the confirmation fails, so it can be tried again" (`VenueBookingRequestPage.test.jsx`)

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 32 |
| AC2 | 11, 12, 13, 14, 15, 24, 33; calendar TC-87-21 |
| AC3 | 16, 17, 18, 19, 20, 21, 22, 23, 24, 25 |
| AC4 | 18, 26, 33, 34 |
| AC5 | 27, 28 |
| AC6 | 29, 30, 34 |
| AC7 | 31 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 02, 04, 18 |
| Negative | 05, 06, 07, 08, 09, 13, 14, 15, 17, 22, 23, 26, 27, 28, 29, 30 |
| Boundary | 03, 11, 12, 16, 19, 20, 21, 24, 31 |
| Concurrency | 10 |
| Configuration | 25 |
| Frontend | 32, 33, 34 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Is confirming a hold checked as approving is, with the event still approved and no conflicts recorded since? Assumed yes. | A2, TC-86-06, 08 |
| Q2 | How close to the 24-hour mark and the expiry must the notices arrive? Assumed within 5 minutes, as the check runs every 5 minutes. | A4, TC-86-25 |
| Q3 | Should a hold placed or changed with less than 24 hours left still get a separate 24-hour warning? Assumed not (scrum lead, 29 Oct 2026). | A4, TC-86-19, 20 |
| Q4 | Should Venue Staff be told when a coordinator confirms a hold (assumed, scrum lead 29 Oct 2026), and when a hold expires (assumed not)? | A5, TC-86-04 |
| Q5 | Should holds that expired before this is released be notified on the first check (assumed), or recorded as Expired without a notice? | A4 |
| Q6 | Can a coordinator cancel an expired hold? Assumed there is nothing to cancel, so it isn't offered. | A3, TC-86-33 |
