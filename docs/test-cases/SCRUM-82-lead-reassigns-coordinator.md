# SCRUM-82 — Event Coordinator Lead Reassigns an Event to a Different Coordinator: Test Cases

**User story:** As an Event Coordinator Lead, I want to reassign an event to a different coordinator, so that the event keeps one responsible coordinator when circumstances change.

**Created:** 17 Oct 2026 · **Status of all cases:** Automated cases pass (17 Oct 2026, local PostgreSQL + Vitest; no schema change). · **Automated tests:** `backend/tests/test_lead_reassign_coordinator.py`; updated: `test_event_coordinator.py` (SCRUM-33), `test_authorization.py`, `test_authorization_unit.py`, `test_authorization_http_unit.py` (SCRUM-27), `test_managed_events.py` (TC-62-04), `test_lead_assigned_events.py` (TC-83-13); `frontend/src/pages/ReassignCoordinatorPage.test.jsx`, `frontend/src/pages/LeadAssignedEventsPage.test.jsx` · **Endpoints:** `GET /api/events/<id>/eligible-coordinators`, `PUT /api/events/<id>/coordinator` (SCRUM-33, changed) · **Related:** Week 7 customer change 5, SCRUM-83 (the Lead's assigned events), SCRUM-81 (assigning from the queue), SCRUM-61 (a coordinator asks for a reassignment), SCRUM-27/33 (the existing reassign function)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The Lead can choose an event from the list of the active events they assigned and start a reassignment from it. |
| AC2 | The Lead can reassign an event to a different eligible coordinator. The old assignment is replaced, so an event never has two main coordinators. The change records the new coordinator, the Lead and the time. |
| AC3 | After reassignment the event appears for the new coordinator and no longer for the previous one. A coordinator sees only events assigned to them. |
| AC4 | The new coordinator is notified, and so is the previous coordinator. |
| AC5 | Choosing the coordinator the event already has is refused with a message and nothing changes. |
| AC6 | Only the Lead can reassign. Anyone else is denied and nothing changes. |
| AC7 | If no other eligible coordinator exists or the save fails, the user is told and the assignment is unchanged. |

## What changes from SCRUM-27/33

The existing reassign function (`PUT /api/events/<id>/coordinator`, with its list `GET /api/events/<id>/eligible-coordinators`) let **administrators and the event's current coordinator** reassign. AC6 makes it **Lead-only**; this was agreed with the team on 17 Oct 2026, so there is one reassign function. A coordinator who wants to hand an event over asks through SCRUM-61 instead.

Following the Week 7 *Guide to Managing Changes*, the affected SCRUM-27/33 tests keep their names and IDs where they still apply, with the caller changed to a Lead and the admin and current coordinator moved to the refused callers. TC-62-04 and TC-83-13, which used an administrator to reassign, now use a Lead.

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Who:** a user whose stored role is `coordinator_lead` (SCRUM-83), read from the database on every request. Any Lead may reassign any event that has a coordinator, not only the ones they assigned; the SCRUM-83 list is the entry point (AC1). Administrators and coordinators get HTTP 403, with no event or coordinator data. *(Q1, Q2)*
- **A2 — Which events (unchanged from SCRUM-33):** an event with a coordinator and a status other than `draft` or `cancelled`. An event with no coordinator is refused with HTTP 409 (`reason: "not_assigned"`) and pointed to the SCRUM-81 queue assignment; draft and cancelled events with HTTP 409. *(Q3)*
- **A3 — Eligible (unchanged):** any user whose current role is `coordinator`, other than the event's current coordinator.
- **A4 — What is recorded:** `coordinator_id` is replaced (one column, so never two main coordinators), with `coordinator_assigned_by_id` (the Lead) and `coordinator_assigned_at` (naive UTC). The event therefore moves to the reassigning Lead's SCRUM-83 list.
- **A5 — Notifications:** the new coordinator gets an in-app `coordinator_assigned` notification and the previous one a `coordinator_unassigned` notification, saved in the same commit as the change. An email to each is queued after the commit; a queue failure does not undo anything, and the reply says the emails were not all queued. *(Q4)*
- **A6 — Same coordinator, nobody eligible, failures:** choosing the current coordinator is HTTP 409; a user who is not an eligible coordinator is HTTP 422, which says so explicitly when no other eligible coordinator exists; a failed save is HTTP 503 with `retryable: true`. None of them change anything or notify anyone.
- **A7 — The reassign page:** each row of the SCRUM-83 list links to `/events/<id>/change-coordinator`, which shows the event, its current coordinator and the eligible coordinators. The list endpoint also returns the event summary and current coordinator for this page.

## Endpoints under test

- `GET /api/events/<id>/eligible-coordinators` → **200** `{"event_id", "event": {"id", "title", "start_time", "status"}, "current_coordinator": {"id", "email"}, "coordinators": [{"id", "email"}], "message": str | null}`. `event` and `current_coordinator` are new; `message` explains an empty list.
- `PUT /api/events/<id>/coordinator` with `{"coordinator_id": int}` → **200** `{"message", "event_id", "coordinator", "previous_coordinator", "assigned_by", "assigned_at", "notification": {"in_app": true, "email_queued": bool}}`. `previous_coordinator`, `assigned_by` and `notification` are new.
- Both: **401** without a valid session; **404** unknown event; **403** anyone who is not a Lead; **409** `{"error", "reason": "not_assigned", "next_step"}` for an event with no coordinator, or **409** for a draft or cancelled event; **503** `{"error", "retryable": true}`.
- PUT only: **400** malformed body or extra fields; **409** the current coordinator; **422** not an eligible coordinator.

## Seed data (RA-SEED)

Users come from `backend/tests/seed_data.py` (`USERS`, and `LEADS`: lena, liam and lucy).

| Ref | Title | Status | Coordinator | Assigned by |
|-----|-------|--------|-------------|-------------|
| E1 | Harbour Lights Festival | submitted | alice | lena |
| E2 | Alumni Mixer | approved | ben | lena |
| E3 | Product Launch | submitted | ben | liam |
| W1 | Tech Summit 2026 | submitted | *none* | — |
| C1 | Cancelled Meetup | cancelled | alice | lena |

All assignments were made on 1 Sep 2026 10:00 (UTC).

---

## AC1 — Starting a reassignment from the Lead's list

**TC-82-01 · Every event in the Lead's list can be opened for reassignment**
- **Traces to:** AC1 · **Type:** Happy path
- **Steps:** As lena, load her SCRUM-83 list; for each event, load its eligible coordinators.
- **Expected result:** HTTP 200 for E1 and E2. E1's reply has its id, title, proposed date and status, `current_coordinator` alice, and eligible coordinators ben and chloe (not alice). `message` is `null`.
- **Automated:** `test_every_event_in_the_leads_list_can_be_opened_for_reassignment`

## AC2 — Reassigning

**TC-82-02 · Reassigning replaces the coordinator and records the Lead and the time**
- **Traces to:** AC2 · **Type:** Happy path
- **Steps:** As lena, reassign E1 from alice to chloe.
- **Expected result:** HTTP 200. E1's coordinator is chloe (alice is no longer), assigned by lena, at a time between the request's start and end. The reply names chloe, alice as the previous coordinator, lena, and the same time.
- **Automated:** `test_reassignment_replaces_the_coordinator_and_records_the_lead_and_time`

**TC-82-03 · Another Lead can reassign, and the event moves to their list**
- **Traces to:** AC2 · **Type:** Happy path · **Depends on:** Q1
- **Steps:** As liam, reassign E1 (assigned by lena) to chloe; load both Leads' SCRUM-83 lists.
- **Expected result:** HTTP 200. E1 is in liam's list with coordinator chloe, and no longer in lena's.
- **Automated:** `test_another_lead_can_reassign_and_the_event_moves_to_their_list`

**TC-82-04 · Events with no coordinator, and draft or cancelled events, cannot be reassigned**
- **Traces to:** AC2 · **Type:** Negative (state) · **Depends on:** Q3
- **Steps:** As lena, load and reassign W1 (no coordinator) and C1 (cancelled).
- **Expected result:** HTTP 409 each time. W1's refusal has `reason: "not_assigned"` and `next_step` `POST /api/events/<W1>/assignment`. Nothing changes.
- **Automated:** `test_unassigned_and_cancelled_events_cannot_be_reassigned`

## AC3 — The event follows the new coordinator

**TC-82-05 · The event appears for the new coordinator and not the previous one**
- **Traces to:** AC3 · **Type:** Happy path
- **Steps:** After TC-82-02, load alice's and chloe's managed events (SCRUM-62) and E1's planning view (SCRUM-34) as each, with tokens issued before the change.
- **Expected result:** E1 is in chloe's list and not alice's. chloe can open its planning view; alice gets HTTP 403.
- **Automated:** `test_event_appears_for_the_new_coordinator_and_not_the_previous_one`

## AC4 — Both coordinators are notified

**TC-82-06 · The new and the previous coordinator are notified in the app and by email**
- **Traces to:** AC4 · **Type:** Happy path · **Depends on:** Q4
- **Expected result:** After TC-82-02, E1 has exactly two new notifications: chloe's (`coordinator_assigned`) and alice's (`coordinator_unassigned`), each naming the event. One email is queued to each, naming the event. The reply has `notification: {"in_app": true, "email_queued": true}`.
- **Automated:** `test_new_and_previous_coordinators_are_notified`

**TC-82-07 · An email queue failure does not undo the reassignment**
- **Traces to:** AC4 · **Type:** Negative (failure)
- **Preconditions:** Queuing an email raises an error.
- **Expected result:** HTTP 200. The reassignment and both in-app notifications are saved; the reply has `email_queued: false`.
- **Automated:** `test_email_queue_failure_keeps_the_reassignment_and_notifications`

## AC5 — The coordinator the event already has

**TC-82-08 · Choosing the current coordinator is refused and nothing changes**
- **Traces to:** AC5 · **Type:** Negative (business rule)
- **Steps:** As lena, reassign E1 to alice.
- **Expected result:** HTTP 409 with a message saying alice is already the coordinator. E1 is unchanged (coordinator, assigner and time); no notification or email.
- **Automated:** `test_choosing_the_current_coordinator_is_refused`

## AC6 — Only the Lead

**TC-82-09 · Everyone else is denied, including administrators and the current coordinator**
- **Traces to:** AC6 · **Type:** Negative (authorisation) · **Depends on:** Q2
- **Steps:** As admin, alice (E1's coordinator), ben, dana (E1's organiser), farah, gus and hana, load E1's eligible coordinators and reassign it to chloe.
- **Expected result:** HTTP 403 every time, with no event title, coordinator email or coordinator list. E1 is unchanged; no notification or email.
- **Automated:** `test_only_leads_can_reassign`

**TC-82-10 · A valid session is required, and role changes apply at once**
- **Traces to:** AC6 · **Type:** Negative (authorisation)
- **Steps:** Reassign E1 with no token, an expired token and a deleted Lead's token; then as lena after her role is changed to coordinator, with her earlier token.
- **Expected result:** HTTP 401 for the session cases and HTTP 403 for lena; E1 is unchanged.
- **Automated:** `test_a_valid_session_and_the_lead_role_are_required`

## AC7 — Nobody else eligible, or the save fails

**TC-82-11 · No other eligible coordinator exists**
- **Traces to:** AC7 · **Type:** Empty state
- **Preconditions:** Every coordinator except alice, real ones included, is given another role inside the test's transaction.
- **Expected result:** E1's eligible list is empty with a message. Reassigning E1 to ben (no longer a coordinator) is HTTP 422 with a message saying no other eligible coordinator is available. E1 is unchanged; no notification or email.
- **Automated:** `test_no_other_eligible_coordinator_is_reported_and_nothing_changes`

**TC-82-12 · The save fails**
- **Traces to:** AC7 · **Type:** Negative (failure)
- **Preconditions:** Committing raises `SQLAlchemyError`.
- **Expected result:** HTTP 503 with `retryable: true` and a message saying the assignment could not be saved and to try again. E1 is unchanged; no notification or email. Reassigning again with the database working succeeds.
- **Automated:** `test_save_failure_changes_nothing_and_retry_works`

## Frontend

**TC-82-13 · Each event in the Lead's list links to its reassign page**
- **Traces to:** AC1 · **Type:** Frontend
- **Expected result:** Each event on "Events I assigned" has a "Reassign coordinator" link to `/events/<id>/change-coordinator`.
- **Automated:** `LeadAssignedEventsPage.test.jsx`

**TC-82-14 · The reassign page shows the event, its coordinator and the choices**
- **Traces to:** AC1, AC2 · **Type:** Frontend
- **Expected result:** "Reassign coordinator" shows the event's name, proposed date and status, "Current coordinator: <email>", and a "New coordinator" box listing each eligible coordinator.
- **Automated:** `ReassignCoordinatorPage.test.jsx`

**TC-82-15 · Reassigning confirms and says both coordinators were notified**
- **Traces to:** AC2, AC4 · **Type:** Frontend
- **Expected result:** Choosing a coordinator and pressing "Reassign coordinator" sends `{coordinator_id}`, then shows the server's confirmation, the new current coordinator, and that both coordinators were notified (or that an email could not be sent). Pressing it with no choice asks for one and sends nothing.
- **Automated:** `ReassignCoordinatorPage.test.jsx`

**TC-82-16 · Refusals and failures**
- **Traces to:** AC5, AC6, AC7 · **Type:** Frontend
- **Expected result:**
  - A 409 on saving (e.g. the same coordinator) shows its message, with no confirmation.
  - A 403 shows its message with no event information, no form and no Retry button.
  - With no eligible coordinator, the server's message is shown and no form.
  - A failed save keeps the choice so the Lead can try again; a failed load shows the error with a Retry button.
- **Automated:** `ReassignCoordinatorPage.test.jsx`

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 13, 14 |
| AC2 | 02, 03, 04, 14, 15 |
| AC3 | 05 |
| AC4 | 06, 07, 15 |
| AC5 | 08, 16 |
| AC6 | 09, 10, 16 |
| AC7 | 11, 12, 16 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 02, 03, 05, 06 |
| Negative | 04, 07, 08, 09, 10, 12 |
| Empty state | 11 |
| Frontend | 13, 14, 15, 16 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | May any Lead reassign any event, or only the events that Lead assigned? Assumed any Lead; the event then moves to that Lead's list. | A1, TC-82-03 |
| Q2 | Should administrators keep a way to reassign (for example when no Lead is available)? Assumed not: only Leads reassign, and coordinators ask through SCRUM-61. | A1, TC-82-09 |
| Q3 | Can events that are rejected or completed still be reassigned, or only active ones? Assumed the existing rule: anything but draft and cancelled. | A2, TC-82-04 |
| Q4 | Should the event's organiser also be told when its coordinator changes? Assumed not; only the two coordinators are notified. | A5, TC-82-06 |
