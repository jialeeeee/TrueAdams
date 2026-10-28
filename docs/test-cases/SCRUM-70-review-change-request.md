# SCRUM-70 — Review Change Request to a Submitted Event: Test Cases

**User story:** As an Event Coordinator, I want to review a change request on an event I coordinate and accept or reject it so that changes are approved only after I understand what they affect.

**Created:** 28 Oct 2026 · **Status of all cases:** automated cases pass (28 Oct 2026, local PostgreSQL as in CI + Vitest); end-to-end check passed in the browser, see [the DoD evidence](../evidence/SCRUM-70-dod-evidence.md) · **Builds on:** SCRUM-46 (the organiser's change request, `event_change_requests`) · **Automated tests:** `backend/tests/test_change_request_review.py` (through the API), `backend/tests/test_change_request_review_unit.py` (the rules, no database), `frontend/src/pages/ChangeRequestReviewPage.test.jsx`, `frontend/src/pages/ChangeRequestsToReviewPage.test.jsx` (+ the outcome in `ChangeRequestPage.test.jsx`) · **Endpoints:** `GET /api/events/change-requests`, `GET /api/events/<id>/change-requests/<request id>`, `POST /api/events/<id>/change-requests/<request id>/decision` · **Related:** SCRUM-44 (an event's new times release its equipment reservations), SCRUM-45/68 (registrations), SCRUM-83 (the Lead's queue of events waiting for a coordinator), SCRUM-85 (several venue bookings per event)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | I can request a change only for my own events, and only when the event status is Approved. Events that are draft, submitted, under review, rejected or cancelled cannot have a change request. |
| AC2 | For a significant change (date, time, attendance, venue or equipment requirements), I can see which venue bookings, equipment arrangements and registrations it affects before deciding. |
| AC3 | I can accept or reject a pending request. The decision and the decision time are saved, and the organiser can see the outcome. |
| AC4 | Rejecting a request requires a reason (not blank, at most 500 characters) that the organiser can see. |
| AC5 | If the event has no assigned coordinator (it is still in the Lead's queue), submission is blocked and I am told the event is waiting for a coordinator. |
| AC6 | If saving the decision fails, the request and event state are unchanged and an error message is shown. |
| AC7 | The organiser is notified of the decision. |
| AC8 | Accepting a request applies the proposed values to the event, and the event shows the new values. |
| AC9 | When an accepted change alters the date, time or venue, every attendee registered for the event is notified of the new details. Unregistered attendees are not notified. |

## Working assumptions (to confirm)

- **A1 — Who reviews:** the event's current coordinator (`is_current_coordinator`: the `coordinator` role and `event.coordinator_id`). Everyone else gets 403 without the request's details. AC1 repeats SCRUM-46's rule for *submitting* (the event's organiser, approved events only), which is unchanged. A request can be decided only while its event is approved: if the event is no longer approved (for example it was cancelled), the request stays pending and deciding is refused with 409 `not_approved`. *(Q1, Q5)*
- **A2 — Every requested field is significant:** SCRUM-46 lets an organiser change the start, end, expected attendance, venue requirements and equipment requirements, and AC2 calls all of these significant. The venue itself can't be changed through a change request (SCRUM-46 A2, Q3), so no request changes it. *(Q2)*
- **A3 — What a change affects (AC2):** worked out from what is recorded now, before deciding. Only *live* arrangements are listed: pending, confirmed and unexpired tentative venue bookings; equipment requirements; reserved (not released) equipment; registered (not withdrawn or cancelled) attendees.
  - **New date or time:** every live venue booking, since each was booked for the current times and is not moved automatically *(Q3)*; every equipment requirement holding reserved equipment, which accepting releases (SCRUM-44 A10); the registered attendees, who will be told the new details (AC9); and registration closing after the new start, if it does *(Q4)*.
  - **New expected attendance:** each live venue booking whose venue holds fewer people than the new attendance (a venue whose capacity is not recorded is not listed); registration, when more people are already registered, or more places are set, than the new attendance.
  - **New venue requirements:** every live venue booking, since Venue Staff assessed it against the current requirements.
  - **New equipment requirements:** every recorded equipment requirement, since the coordinator recorded them from the current note (SCRUM-42).
  - Each listed item says why. When nothing recorded is affected, the review says so.
  - The impact is shown only while the request is pending. Once it is decided, the event's arrangements no longer describe what the request would change, so the review of a decided request has none (`impact: null`).
- **A4 — Deciding:** `{"decision": "accept" | "reject", "reason": …}`. The whole request is accepted or rejected, not field by field *(Q6)*. The request's status becomes `accepted` ("Accepted") or `rejected` ("Rejected"), with when (naive UTC) and by whom. A decided request can't be decided again (409 `decided`). With nothing pending, the organiser may submit a new request (SCRUM-46 A6).
- **A5 — Rejection reason (AC4):** required to reject; it must contain a visible character (as SCRUM-60 A3) and be at most 500 characters after trimming. It is saved trimmed and shown to the organiser. A reason sent with an acceptance is ignored: the review page only offers it for rejecting.
- **A6 — Accepting (AC8):** the proposed values replace the event's start, end, expected attendance, venue requirements or equipment requirements, in the same commit as the decision. Everything else on the event is unchanged. A new start or end releases the event's reserved equipment through SCRUM-44's rule. Venue bookings, the equipment requirements and the registration settings are not changed: the coordinator rebooks or updates them afterwards *(Q3, Q4)*.
- **A7 — Notifications:**
  - The organiser gets an in-app notification (`change_request_accepted` or `change_request_rejected`) naming the event, the outcome, who decided and when, and the changes or the reason, then an email (AC7).
  - When an accepted request changes the start or end, every attendee with a `registered` registration gets an in-app notification (`event_details_changed`) with the event's new start, end and venue, then an email (AC9). Withdrawn and cancelled registrations, and other users, get nothing. Rejected requests and accepted ones that leave the times alone notify no attendee *(Q7)*.
  - Notifications are saved in the same commit as the decision. Emails are queued afterwards; if one can't be queued the decision stands, no further emails are tried, and the reply says `email_queued: false`.
- **A8 — Order of checks:** 401 (no valid user) → 404 (no such event, or no such request for it) → 403 (not the event's current coordinator) → 400 (body not a JSON object, decision missing or unknown, reason missing, blank or too long) → 409 (`decided`, then `not_approved`) → 503 (not saved, `retryable: true`). The event, then the request, are read `FOR UPDATE`, as submitting a request locks the event, so a decision and a new request, or two decisions, happen one at a time.
- **A9 — Waiting for a coordinator (AC5):** SCRUM-46 already blocks submission when the event has no current coordinator (409 `no_coordinator`). Its message now says the event is waiting for a coordinator: "This event is waiting for a coordinator to be assigned, so there is nobody to review a change request yet. Please try again once a coordinator is assigned."
- **A10 — Finding requests:** the coordinator's "Change requests to review" page lists the pending requests of the events they currently coordinate, oldest first, each linking to its review page.

## Seed data (CV-SEED)

Users: `USERS` from `backend/tests/seed_data.py` (alice and ben coordinators; dana organiser; farah attendee), plus attendees **gail** and **hugo** and Lead **lena**.

| Key | Event | Status | Organiser | Coordinator | Start – end | Attendance | Venue requirements | Equipment requirements |
|-----|-------|--------|-----------|-------------|-------------|------------|--------------------|------------------------|
| V1 | Charity Gala | approved | dana | alice | 2026-12-05 18:00 – 23:00 | 200 | Ballroom for 200 | 2 wireless microphones |
| V2 | Product Launch | approved | dana | ben | 2026-12-20 14:00 – 18:00 | 50 | Auditorium | Projector |
| V3 | Winter Concert | cancelled | dana | alice | 2026-12-15 19:00 – 22:00 | 300 | Concert hall | (none) |

V1 also has registration capacity 210, closing 2026-12-01 12:00, and:

| Key | What | Details |
|-----|------|---------|
| B1 | Venue booking | Grand Ballroom (capacity 220), **confirmed**, 2026-12-05 18:00–23:00 |
| B2 | Venue booking | Garden Room (capacity 120), **tentative**, 2026-12-05 17:00–19:00, hold expires 2026-11-30 12:00 |
| B3 | Venue booking | Rooftop (capacity not recorded), **pending**, 2026-12-05 21:00–23:00 |
| B4 | Venue booking | Garden Room, **rejected** |
| B5 | Venue booking | Grand Ballroom, **tentative**, hold **expired** 2026-10-01 12:00 |
| Q1 | Equipment requirement | "Wireless microphone" × 2, 2 reserved (reservation R1) |
| Q2 | Equipment requirement | "Projector" × 1, nothing reserved; an earlier reservation R2 was released |
| — | Registrations | farah and gail **registered**; hugo **withdrawn** |

Change requests, each by dana and pending unless stated:

| Key | Event | Changes |
|-----|-------|---------|
| T1 | V1 | Start 2026-12-05 18:00 → 2026-12-06 18:00; End 2026-12-05 23:00 → 2026-12-06 23:30 |
| N1 | V1 | (alternative to T1) Expected attendance 200 → 250 |
| S1 | V1 | (alternative to T1) Venue requirements → "Ballroom and breakout room"; Equipment requirements → "4 wireless microphones" |
| P1 | V2 | Expected attendance 50 → 60 |
| X1 | V3 | Expected attendance 300 → 320 |

V1 has at most one pending request at a time (SCRUM-46 A6), so each test seeds T1, N1 or S1 as it needs.

---

## AC1 — Only the event's coordinator, and only for an approved event

**TC-70-01 · The coordinator opens a pending change request**
- **Traces to:** AC1, AC2 · **Type:** Positive · **Depends on:** A1, A3
- **Steps:** With T1 pending, as alice, `GET /api/events/<V1>/change-requests/<T1>`.
- **Expected result:** HTTP 200 with V1's title, status and organiser; T1 with its changes (field, label, from, to), Pending Review; its impact; `can_decide: true`.
- **Automated:** `test_tc_70_01_the_coordinator_opens_a_pending_request`

**TC-70-02 · Who may review and decide, in what order**
- **Traces to:** AC1 · **Type:** Negative (authorisation) · **Depends on:** A1, A8
- **Steps:** Open and decide T1 with no token; with a deleted user's token; for a missing event; for a missing request; for P1 under V1's address; as ben (another coordinator), dana (the organiser), farah, admin and lena (a Lead).
- **Expected result:** 401; 401 ("Your session is no longer valid"); 404; 404; 404; 403 each, without T1's changes or V1's title. T1 stays pending; V1 is unchanged.
- **Automated:** `test_tc_70_02_who_may_review_and_in_what_order`

**TC-70-03 · A request on an event that is no longer approved can't be decided**
- **Traces to:** AC1 · **Type:** Negative · **Depends on:** A1
- **Steps:** As alice, open X1 (V3 is cancelled), then accept it, then reject it with a reason.
- **Expected result:** The review says `can_decide: false`, `blocked_reason: "not_approved"`, naming the status. Both decisions are refused with 409, `reason: "not_approved"`. X1 stays pending; V3 is unchanged; nobody is notified.
- **Automated:** `test_tc_70_03_a_request_on_an_event_no_longer_approved_cannot_be_decided`

**TC-70-04 · The coordinator's list of change requests to review**
- **Traces to:** AC1, AC3 · **Type:** Positive · **Depends on:** A10
- **Steps:** With T1, P1 and X1 pending and an accepted request on V1 from earlier, as alice and as ben, `GET /api/events/change-requests`; as dana; then as chloe (no events).
- **Expected result:** alice sees T1 and X1 (her events), oldest first, each with its event, organiser, requested time and changes; ben sees only P1; neither sees decided requests. dana gets 403. chloe gets an empty list with a message.
- **Automated:** `test_tc_70_04_the_coordinator_lists_their_pending_change_requests`

## AC2 — What the change affects, before deciding

**TC-70-05 · A new date and time: venue bookings, reserved equipment and registrations**
- **Traces to:** AC2 · **Type:** Positive · **Depends on:** A3
- **Steps:** With T1 pending, as alice, open T1.
- **Expected result:** `venue_bookings` lists B1, B2 and B3, each with its venue, period, status and why. `equipment` lists Q1 with 2 reserved, saying they will be released. `registrations` says 2 attendees are registered and will be told the new details. Registration closes 2026-12-01 12:00, before the new start, so no closing problem is listed.
- **Automated:** `test_tc_70_05_a_time_change_lists_bookings_reserved_equipment_and_registrations`

**TC-70-06 · A new expected attendance: venues too small, and registrations above it**
- **Traces to:** AC2 · **Type:** Positive · **Depends on:** A3
- **Steps:** With N1 pending (200 → 250), open it. Then, with a request lowering attendance 200 → 1 instead, open that.
- **Expected result:** For 250: B1 (holds 220) and B2 (holds 120) are listed with their capacity; B3 (capacity not recorded) isn't; no equipment; registration lists nothing (2 registered and 210 places are within 250). For 1: no booking is listed; registration says 2 are registered and 210 places are set, both more than 1.
- **Automated:** `test_tc_70_06_an_attendance_change_lists_small_venues_and_registrations_above_it`

**TC-70-07 · New venue and equipment requirements**
- **Traces to:** AC2 · **Type:** Positive · **Depends on:** A3
- **Steps:** With S1 pending, open it.
- **Expected result:** B1, B2 and B3 are listed as assessed against the current venue requirements; Q1 and Q2 as recorded from the current equipment requirements, Q1 with its 2 reserved. Registration lists nothing.
- **Automated:** `test_tc_70_07_requirement_changes_list_bookings_and_equipment`

**TC-70-08 · Only live arrangements of this event are listed; nothing affected says so**
- **Traces to:** AC2 · **Type:** Negative · **Depends on:** A3
- **Steps:** With T1 pending, open it and look for B4 (rejected), B5 (expired hold), R2 (released) and hugo (withdrawn). Then open P1 (V2 has no bookings, equipment or registrations).
- **Expected result:** None of B4, B5 or R2 is listed and only 2 registered attendees are counted. P1's impact lists nothing and says nothing recorded for the event is affected.
- **Automated:** `test_tc_70_08_only_live_arrangements_of_the_event_are_listed`

**TC-70-09 · A failed read is a failure, not "nothing affected"**
- **Traces to:** AC2, AC6 · **Type:** Negative (failure)
- **Steps:** Make reading the venue bookings fail and open T1.
- **Expected result:** HTTP 503, `retryable: true`, no internal error text, no impact.
- **Automated:** `test_tc_70_09_a_failed_read_is_an_error_not_an_empty_impact`

## AC3 — Accept or reject; the decision and its time are saved; the organiser sees it

**TC-70-10 · Accepting records the decision and its time**
- **Traces to:** AC3 · **Type:** Positive · **Depends on:** A4
- **Steps:** As alice, accept N1.
- **Expected result:** HTTP 200. N1 is `accepted` ("Accepted") with `decided_at` (the time of the decision) and `decided_by` alice; no reason. The reply's message says it was accepted.
- **Automated:** `test_tc_70_10_accepting_records_the_decision_and_its_time`

**TC-70-11 · Rejecting records the decision, its time and the reason**
- **Traces to:** AC3, AC4 · **Type:** Positive · **Depends on:** A4, A5
- **Steps:** As alice, reject N1 with "  The ballroom can't hold 250.  ".
- **Expected result:** HTTP 200. N1 is `rejected` ("Rejected") with `decided_at`, `decided_by` alice and reason "The ballroom can't hold 250.".
- **Automated:** `test_tc_70_11_rejecting_records_the_decision_time_and_reason`

**TC-70-12 · A decided request can't be decided again**
- **Traces to:** AC3 · **Type:** Negative · **Depends on:** A4
- **Steps:** Accept N1, then accept it again, then reject it with a reason; open it.
- **Expected result:** Both repeats are refused with 409, `reason: "decided"`, saying it was already accepted. N1 keeps its first decision; the organiser has one notification. The review shows the decision, `can_decide: false` and no impact.
- **Automated:** `test_tc_70_12_a_decided_request_cannot_be_decided_again`

**TC-70-13 · The organiser sees the outcome, and may ask again**
- **Traces to:** AC3, AC4 · **Type:** Positive · **Depends on:** A4
- **Steps:** Reject N1 with a reason; as dana, open V1's change request form (SCRUM-46); submit a new request.
- **Expected result:** The form's `latest_decision` is N1, Rejected, with the decision time, who decided and the reason; no request is pending, so `can_request: true`. The new request is accepted for review (201).
- **Automated:** `test_tc_70_13_the_organiser_sees_the_outcome_and_may_ask_again`

**TC-70-14 · The decision must be clear**
- **Traces to:** AC3 · **Type:** Negative (validation) · **Depends on:** A8
- **Steps:** Decide N1 with a body that isn't JSON; with `{}`; with `{"decision": "approve"}`; with `{"decision": "accept", "reason": 5}`.
- **Expected result:** HTTP 400 each time, saying what to send. N1 stays pending.
- **Automated:** `test_tc_70_14_the_decision_must_be_clear`

## AC4 — A rejection needs a reason of at most 500 characters

**TC-70-15 · The rejection reason is required and limited**
- **Traces to:** AC4 · **Type:** Boundary · **Depends on:** A5
- **Steps:** Reject N1 with no reason; with ""; with "   "; with a zero-width space; with 501 characters; then with exactly 500 characters (after trimming surrounding spaces).
- **Expected result:** 400 with `field: "reason"` for the first five ("A reason is required…", or saying the limit is 500 characters). The 500-character reason is accepted and saved.
- **Automated:** `test_tc_70_15_the_rejection_reason_is_required_and_limited`

## AC5 — An event waiting for a coordinator can't take a request

**TC-70-16 · Submission says the event is waiting for a coordinator**
- **Traces to:** AC5 · **Type:** Negative · **Depends on:** A9
- **Steps:** Seed an approved event of dana's with no coordinator (in the Lead's queue). As dana, open its change request form, then submit an attendance change.
- **Expected result:** The form and the 409 (`reason: "no_coordinator"`) both say the event is waiting for a coordinator. Nothing is saved.
- **Automated:** `test_tc_70_16_an_event_waiting_for_a_coordinator_cannot_take_a_request`

## AC6 — A failed save changes nothing

**TC-70-17 · A failed save leaves the request and the event unchanged**
- **Traces to:** AC6 · **Type:** Negative (failure) · **Depends on:** A7
- **Steps:** With T1 pending, make saving fail in turn: the request's decision, the event's new values, the organiser's notification, an attendee's notification; each time accept T1. Then make saving the decision fail while rejecting.
- **Expected result:** HTTP 503, `retryable: true`, "The decision was not saved, so the change request and the event are unchanged. Please try again.", no internal error text. T1 stays pending; V1 keeps its values; R1 is still reserved; nobody is notified; no email.
- **Automated:** `test_tc_70_17_a_failed_save_leaves_the_request_and_event_unchanged`

**TC-70-18 · The event and the request are locked before the decision is checked**
- **Traces to:** AC6 · **Type:** Business rule (concurrency) · **Depends on:** A8
- **Steps:** Accept N1 and record the SQL sent.
- **Expected result:** V1 is read `FOR UPDATE`, then N1 is read `FOR UPDATE`, before anything is written.
- **Automated:** `test_tc_70_18_the_event_and_request_are_locked_before_deciding`

## AC7 — The organiser is notified

**TC-70-19 · The organiser is told the decision**
- **Traces to:** AC7, AC4 · **Type:** Positive · **Depends on:** A7
- **Steps:** Accept T1. Separately, reject N1 with a reason.
- **Expected result:** dana gets one `change_request_accepted` notification for V1 naming Charity Gala, "accepted", alice and the changes; and one `change_request_rejected` notification naming the reason. Each is emailed to dana. `notification.in_app` is true and `email_queued` true.
- **Automated:** `test_tc_70_19_the_organiser_is_told_the_decision`

**TC-70-20 · An email that can't be queued doesn't undo the decision**
- **Traces to:** AC7 · **Type:** Negative (failure) · **Depends on:** A7
- **Steps:** Make queuing emails fail and accept T1.
- **Expected result:** HTTP 200 with `email_queued: false`; T1 is accepted, V1 has the new times, and the in-app notifications are saved. Only one email was attempted.
- **Automated:** `test_tc_70_20_an_email_queue_failure_does_not_undo_the_decision`

## AC8 — Accepting applies the proposed values

**TC-70-21 · Accepting applies every proposed value, and only those**
- **Traces to:** AC8 · **Type:** Positive · **Depends on:** A6
- **Steps:** Accept T1, then open V1's planning view as alice. Separately, accept S1, and a request clearing the equipment requirements.
- **Expected result:** V1's start and end are the proposed ones and the planning view shows them; its title, attendance, requirements, venue, coordinator and status are unchanged. S1 sets both requirement texts. The cleared request leaves no equipment requirements recorded.
- **Automated:** `test_tc_70_21_accepting_applies_every_proposed_value`

**TC-70-22 · Rejecting leaves the event unchanged**
- **Traces to:** AC8 · **Type:** Negative · **Depends on:** A6
- **Steps:** Reject T1 with a reason.
- **Expected result:** V1 keeps its start and end; R1 is still reserved.
- **Automated:** `test_tc_70_22_rejecting_leaves_the_event_unchanged`

**TC-70-23 · New times release the reserved equipment; bookings stay for the coordinator to handle**
- **Traces to:** AC8, AC2 · **Type:** Business rule · **Depends on:** A6
- **Steps:** Accept T1.
- **Expected result:** R1 is released with SCRUM-44's reason "The event's times were changed."; the reply says the reserved equipment was released. B1, B2 and B3 are unchanged. Accepting N1 (attendance only) instead releases nothing.
- **Automated:** `test_tc_70_23_new_times_release_reserved_equipment_and_leave_bookings`

## AC9 — Registered attendees are told new details

**TC-70-24 · Every registered attendee is told the new date and time**
- **Traces to:** AC9 · **Type:** Positive · **Depends on:** A7
- **Steps:** Accept T1.
- **Expected result:** farah and gail each get one `event_details_changed` notification for V1 with "Charity Gala", the new start and end (2026-12-06 18:00 to 2026-12-06 23:30) and the venue (Grand Ballroom); each is emailed. hugo (withdrawn), dana, the coordinator and a registered attendee of V2 get none. The reply says 2 registered attendees were told.
- **Automated:** `test_tc_70_24_every_registered_attendee_is_told_the_new_details`

**TC-70-25 · No attendee is told when the times don't change**
- **Traces to:** AC9 · **Type:** Negative · **Depends on:** A7
- **Steps:** Accept N1 (attendance only). Separately, reject T1 with a reason.
- **Expected result:** No `event_details_changed` notification and no email to farah, gail or hugo either time.
- **Automated:** `test_tc_70_25_no_attendee_is_told_when_the_times_do_not_change`

## The rules without a database (`test_change_request_review_unit.py`)

The impact rules on plain values (A3): which bookings each kind of change affects and why, venue capacity against the new attendance, registrations above it, registration closing after the new start, reserved equipment on a time change, and the "nothing affected" case; the decision and reason rules (A4, A5); and the values an accepted request applies (A6). **Automated:** `ImpactRuleTests`, `DecisionRuleTests`, `AppliedValueTests`.

## Frontend

`ChangeRequestsToReviewPage` (`/events/change-requests`, "Change requests to review" in the navigation) and `ChangeRequestReviewPage` (`/events/:eventId/change-requests/:requestId`); the organiser's outcome on `ChangeRequestPage`.

**TC-70-26 · The review shows the changes and what they affect** — AC2 · `shows the requested changes and what they affect`

**TC-70-27 · Accepting confirms the decision and shows it** — AC3, AC8 · `accepts the request and shows the decision`

**TC-70-28 · Rejecting needs a reason of at most 500 characters** — AC4 · `requires a reason of at most 500 characters to reject`

**TC-70-29 · A failed decision explains itself and keeps the reason** — AC6 · `keeps the reason after a failed decision so it can be tried again`

**TC-70-30 · A request that can't be decided says why and offers no buttons** — AC1, AC3 · `explains why a request can't be decided`

**TC-70-31 · The list links to each pending request** — AC1 · `lists the pending change requests with links to review them`

**TC-70-32 · The organiser sees the outcome of their last request** — AC3, AC4 · `ChangeRequestPage` "shows the outcome of the last decided request"

Also: failed loads explain themselves and offer Retry on both pages.

---

## Traceability matrix

| AC | Test cases |
|----|------------|
| AC1 | 01, 02, 03, 04, 30, 31 |
| AC2 | 01, 05, 06, 07, 08, 09, 23, 26 |
| AC3 | 04, 10, 11, 12, 13, 14, 27, 30, 32 |
| AC4 | 11, 13, 15, 19, 28, 32 |
| AC5 | 16 |
| AC6 | 09, 17, 18, 29 |
| AC7 | 19, 20 |
| AC8 | 21, 22, 23, 27 |
| AC9 | 24, 25 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | AC1 repeats the organiser's rule for submitting a change request. Is anything meant to change for submitting, or is it there to say a coordinator only reviews requests on approved events they coordinate (as built)? | A1, TC-70-03 |
| Q2 | AC2 and AC9 mention the venue, but a change request can't change the venue (SCRUM-46 Q3). Should it be able to? | A2 |
| Q3 | When new times are accepted, should the event's venue bookings be moved, cancelled or left for the coordinator to rebook (as built: left, and listed as affected)? | A3, A6, TC-70-23 |
| Q4 | If new times start before registration closes, should accepting be refused, should registration close earlier automatically, or should the coordinator fix it (as built: listed as affected only)? | A3, A6 |
| Q5 | May a coordinator still reject a pending request after the event is cancelled (as built: no; it stays pending)? | A1, TC-70-03 |
| Q6 | May a coordinator accept part of a request? | A4 |
| Q7 | Should registered attendees also be told of other accepted changes, such as the venue requirements? | A7, TC-70-25 |
