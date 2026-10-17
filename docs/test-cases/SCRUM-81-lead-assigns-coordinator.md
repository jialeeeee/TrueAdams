# SCRUM-81 — Event Coordinator Lead Assigns a Coordinator to a Waiting Event: Test Cases

**User story:** As an Event Coordinator Lead, I want to assign a coordinator to an event in the queue, so that the event has one responsible coordinator.

**Created:** 17 Oct 2026 · **Status of all cases:** Automated cases pass (17 Oct 2026, local Postgres, Supabase and Vitest). · **Automated tests:** `backend/tests/test_lead_assign_coordinator.py`, `frontend/src/pages/AssignCoordinatorPage.test.jsx` · **Endpoints:** `GET /api/events/<id>/assignment`, `POST /api/events/<id>/assignment` (new) · **Related:** Week 7 customer change 5 (Event Coordinator Lead role), SCRUM-83 (the Lead's assigned events), SCRUM-27/33 (reassigning a coordinator), SCRUM-28 (submission)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The Lead can choose an eligible coordinator for an event in the queue. The assignment records the coordinator, the Lead and the time, and the event leaves the queue. |
| AC2 | The newly assigned coordinator is notified. |
| AC3 | If the event already has a coordinator (for example another Lead assigned it first), the assignment is refused, the Lead is told to use the reassign function, and nothing changes. |
| AC4 | Only the Lead can assign. Anyone else is denied and nothing changes. |
| AC5 | If no eligible coordinator exists or the save fails, the user is told and the assignment is unchanged. |

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — The queue:** an event is waiting in the queue while it is `submitted` and has no coordinator (`ASSIGNMENT_QUEUE_STATUSES` in `app/events/routes.py`). Events in any other status (draft, cancelled, rejected, …) cannot be assigned here. New submissions enter the queue with no coordinator (A9 in [SCRUM-81-unassigned-queue.md](SCRUM-81-unassigned-queue.md), which replaced SCRUM-28's automatic assignment), and the Lead lists them at `GET /api/events/queue`. *(Q1)*
- **A2 — The Lead:** a user whose stored role is `coordinator_lead` (SCRUM-83), read from the database on every request. Any Lead may assign any waiting event. *(Q2)*
- **A3 — Eligible coordinator:** any user whose current role is `coordinator`, the same rule as reassignment (`_eligible_coordinators`). Workload and availability are not considered. *(Q3)*
- **A4 — What is recorded:** `coordinator_id`, `coordinator_assigned_by_id` (the Lead) and `coordinator_assigned_at` (naive UTC), saved together. The event then appears in the Lead's SCRUM-83 list and the coordinator's SCRUM-62 list.
- **A5 — Notification:** the new coordinator gets an in-app `Notification` (kind `coordinator_assigned`), saved in the same commit as the assignment, and an email queued after the commit. A queue failure does not undo the assignment; the reply says the email was not queued.
- **A6 — Already assigned:** HTTP 409 with `reason: "already_assigned"`, a message telling the Lead to use the reassign function, and `next_step` pointing at the existing reassign endpoint (`PUT /api/events/<id>/coordinator`). The event row is locked while it is checked, so when two Leads assign at once, the second is refused. *(Q4)*
- **A7 — Order of checks:** 401 → 404 → 403 → 400 (malformed body) → 409 (not waiting, or already assigned) → 422 (the chosen user is not an eligible coordinator), the same order as the existing reassign endpoint.
- **A8 — Failures:** loading or saving failures return HTTP 503 with `retryable: true` and change nothing. The page keeps the Lead's choice so they can try again.

## Endpoints under test

- `GET /api/events/<id>/assignment` → **200** `{"event": {"id", "title", "start_time", "status"}, "coordinators": [{"id", "email"}], "message": str | null}`. `message` explains an empty `coordinators` list; otherwise `null`.
- `POST /api/events/<id>/assignment` with `{"coordinator_id": int}` → **200** `{"message", "assignment": {"event_id", "coordinator", "assigned_by", "assigned_at"}, "notification": {"in_app": true, "email_queued": bool}}`.
- Both: **401** without a valid session; **404** for an unknown event; **403** for anyone who is not a Lead; **409** `{"error", "reason": "not_in_queue" | "already_assigned", "next_step"?}`; **503** `{"error", "retryable": true}`.
- POST only: **400** `{"error", "field": "coordinator_id"}` for a missing or non-integer `coordinator_id`, or any other field; **422** `{"error", "field": "coordinator_id"}` for a user who is not an eligible coordinator, saying so explicitly when no eligible coordinator exists.

## Seed data (AQ-SEED)

Users come from `backend/tests/seed_data.py` (alice, ben and chloe are coordinators), plus two Leads: lena and liam (`coordinator_lead`).

| Ref | Title | Status | Coordinator | Assigned by |
|-----|-------|--------|-------------|-------------|
| Q1 | Harbour Lights Festival | submitted | *none* | — |
| Q2 | Alumni Mixer | submitted | *none* | — |
| A1 | Product Launch | submitted | ben | liam |
| D1 | Draft Workshop | draft | *none* | — |
| C1 | Cancelled Meetup | cancelled | *none* | — |
| R1 | Startup Expo | rejected | *none* | — |

---

## AC1 — Choosing and assigning a coordinator

**TC-81-01 · The Lead sees the waiting event and its eligible coordinators**
- **Traces to:** AC1 · **Type:** Happy path
- **Steps:** As lena, load Q1's assignment.
- **Expected result:** HTTP 200 with Q1's id, title, proposed date and status. `coordinators` includes alice, ben and chloe and no Lead or other role, ordered by email. `message` is `null`.
- **Automated:** `test_lead_sees_the_waiting_event_and_eligible_coordinators`

**TC-81-02 · Assigning records the coordinator, the Lead and the time**
- **Traces to:** AC1 · **Type:** Happy path
- **Steps:** As lena, assign alice to Q1.
- **Expected result:** HTTP 200. Q1's coordinator is alice, assigned by lena, at a time between the request's start and end. The reply names alice and lena and carries the same time.
- **Automated:** `test_assignment_records_the_coordinator_the_lead_and_the_time`

**TC-81-03 · The event leaves the queue**
- **Traces to:** AC1 · **Type:** Happy path
- **Steps:** After TC-81-02, load Q1's assignment again; load lena's SCRUM-83 list and alice's SCRUM-62 list.
- **Expected result:** Loading the assignment returns HTTP 409 `already_assigned`. Q1 is in lena's list with coordinator alice, and in alice's managed events.
- **Automated:** `test_assigned_event_leaves_the_queue`

**TC-81-04 · Only an eligible coordinator can be chosen**
- **Traces to:** AC1 · **Type:** Negative (input) · **Depends on:** Q3
- **Steps:** As lena, assign Q1 to dana (organiser), liam (Lead), admin, and a user ID that does not exist.
- **Expected result:** HTTP 422 with `field: "coordinator_id"` each time; nothing changes.
- **Automated:** `test_only_an_eligible_coordinator_can_be_chosen`

**TC-81-05 · A malformed request is refused**
- **Traces to:** AC1 · **Type:** Negative (input)
- **Steps:** As lena, send no body, `{}`, `{"coordinator_id": "12"}`, `{"coordinator_id": true}`, and `{"coordinator_id": <alice>, "coordinator_assigned_by_id": <liam>}`.
- **Expected result:** HTTP 400 each time; nothing changes.
- **Automated:** `test_malformed_requests_are_refused`

**TC-81-06 · Events not waiting in the queue cannot be assigned**
- **Traces to:** AC1 · **Type:** Boundary · **Depends on:** Q1
- **Steps:** As lena, load and assign D1, C1 and R1.
- **Expected result:** HTTP 409 with `reason: "not_in_queue"` each time; nothing changes.
- **Automated:** `test_events_not_waiting_in_the_queue_cannot_be_assigned`

## AC2 — The coordinator is notified

**TC-81-07 · The new coordinator gets an in-app notification and an email**
- **Traces to:** AC2 · **Type:** Happy path
- **Expected result:** After TC-81-02, alice has exactly one new `coordinator_assigned` notification for Q1 that names the event. One email to alice is queued, naming the event. The reply has `notification: {"in_app": true, "email_queued": true}`.
- **Automated:** `test_new_coordinator_is_notified_in_app_and_by_email`

**TC-81-08 · An email queue failure does not undo the assignment**
- **Traces to:** AC2 · **Type:** Negative (failure)
- **Preconditions:** Queuing the email raises an error.
- **Expected result:** HTTP 200. The assignment and the in-app notification are saved; the reply has `email_queued: false`.
- **Automated:** `test_email_queue_failure_keeps_the_assignment_and_in_app_notification`

## AC3 — Already assigned

**TC-81-09 · An event with a coordinator is refused, pointing to reassignment**
- **Traces to:** AC3 · **Type:** Negative (state) · **Depends on:** Q4
- **Steps:** As lena, assign alice to A1 (ben's, assigned by liam).
- **Expected result:** HTTP 409 with `reason: "already_assigned"`, a message telling the Lead to use the reassign function, and `next_step` `PUT /api/events/<A1>/coordinator`. A1 is still ben's, assigned by liam at the original time; no notification or email.
- **Automated:** `test_event_with_a_coordinator_is_refused_with_the_reassign_function`

**TC-81-10 · When another Lead assigns first, the second assignment is refused**
- **Traces to:** AC3 · **Type:** Boundary (concurrency)
- **Steps:** liam assigns ben to Q1; lena then assigns alice to Q1.
- **Expected result:** liam's succeeds. lena's gets HTTP 409 `already_assigned`. Q1 stays ben's, assigned by liam; only ben is notified.
- **Automated:** `test_second_lead_is_refused_after_another_lead_assigns_first`

## AC4 — Only the Lead

**TC-81-11 · Every other role is denied and nothing changes**
- **Traces to:** AC4 · **Type:** Negative (authorisation) · **Depends on:** Q2
- **Steps:** As admin, alice, dana, farah, gus and hana, load Q1's assignment and assign alice to it.
- **Expected result:** HTTP 403 every time, with no event title or coordinator list. Q1 is unchanged; no notification or email.
- **Automated:** `test_only_leads_can_assign`

**TC-81-12 · A valid session is required**
- **Traces to:** AC4 · **Type:** Negative (authorisation)
- **Steps:** Load and assign with no token, an expired token and a deleted Lead's token.
- **Expected result:** HTTP 401; nothing changes.
- **Automated:** `test_a_valid_session_is_required`

**TC-81-13 · A Lead whose role changes is denied at once**
- **Traces to:** AC4 · **Type:** Negative (authorisation)
- **Steps:** Change lena's role to coordinator, then assign with her earlier token.
- **Expected result:** HTTP 403; nothing changes.
- **Automated:** `test_lead_whose_role_changes_is_denied_at_once`

**TC-81-14 · An unknown event**
- **Traces to:** AC4 · **Type:** Negative
- **Expected result:** HTTP 404 for both endpoints.
- **Automated:** `test_unknown_event_is_not_found`

## AC5 — No eligible coordinator, or the save fails

**TC-81-15 · No eligible coordinator exists**
- **Traces to:** AC5 · **Type:** Empty state
- **Preconditions:** Every coordinator, real ones included, is given another role inside the test's transaction.
- **Expected result:** Loading Q1's assignment returns `coordinators: []` and a message saying no eligible coordinator is available. Assigning alice returns HTTP 422 with that message; nothing changes.
- **Automated:** `test_no_eligible_coordinator_is_reported_and_nothing_changes`

**TC-81-16 · The save fails**
- **Traces to:** AC5 · **Type:** Negative (failure)
- **Preconditions:** Committing raises `SQLAlchemyError`.
- **Expected result:** HTTP 503 with `retryable: true` and a message saying the assignment was not saved and to try again. Q1 is unchanged; no notification or email. Assigning again with the database working succeeds.
- **Automated:** `test_save_failure_changes_nothing_and_retry_works`

**TC-81-17 · Loading fails**
- **Traces to:** A8 · **Type:** Negative (failure)
- **Preconditions:** Every database query raises `SQLAlchemyError`.
- **Expected result:** HTTP 503 with `retryable: true` and no event data.
- **Automated:** `test_load_failure_is_reported`

## Frontend

**TC-81-18 · The page shows the event and its eligible coordinators**
- **Traces to:** AC1 · **Type:** Frontend
- **Expected result:** "Assign a coordinator" shows the event's name, proposed date (as recorded) and status, and a "Coordinator" box listing each eligible coordinator by email.
- **Automated:** `AssignCoordinatorPage.test.jsx`

**TC-81-19 · Assigning confirms and says the coordinator was notified**
- **Traces to:** AC1, AC2 · **Type:** Frontend
- **Expected result:** Choosing a coordinator and pressing "Assign coordinator" sends `{coordinator_id}` and shows the server's confirmation and that the coordinator was notified (or that the email could not be sent). The form is removed. Pressing it with no choice asks the Lead to choose one and sends nothing.
- **Automated:** `AssignCoordinatorPage.test.jsx`

**TC-81-20 · Already assigned, on loading or on assigning**
- **Traces to:** AC3 · **Type:** Frontend
- **Expected result:** The server's message telling the Lead to use the reassign function is shown and the form is removed; no confirmation is shown.
- **Automated:** `AssignCoordinatorPage.test.jsx`

**TC-81-21 · Anyone else is denied**
- **Traces to:** AC4 · **Type:** Frontend
- **Expected result:** A 403 shows its message with no event information, no form and no Retry button.
- **Automated:** `AssignCoordinatorPage.test.jsx`

**TC-81-22 · No eligible coordinator, save failure and load failure**
- **Traces to:** AC5, A8 · **Type:** Frontend
- **Expected result:** With no eligible coordinator, the server's message is shown and no form. A failed save shows the error, keeps the chosen coordinator and lets the Lead try again. A failed load shows the error (or a fallback for a network failure) with a Retry button.
- **Automated:** `AssignCoordinatorPage.test.jsx`

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 03, 04, 05, 06, 18, 19 |
| AC2 | 07, 08, 19 |
| AC3 | 09, 10, 20 |
| AC4 | 11, 12, 13, 14, 21 |
| AC5 | 15, 16, 22 |
| A8 (load failure) | 17, 22 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 02, 03, 07 |
| Negative | 04, 05, 08, 09, 11, 12, 13, 14, 16, 17 |
| Boundary | 06, 10 |
| Empty state | 15 |
| Frontend | 18, 19, 20, 21, 22 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Which events are "in the queue": only newly submitted ones with no coordinator, or also events whose coordinator left? Assumed submitted and unassigned. | A1, TC-81-06 |
| Q2 | Can any Lead assign any waiting event, or do Leads have their own areas or teams? Assumed any Lead, any event. | A2, TC-81-11 |
| Q3 | What makes a coordinator "eligible": just the role, or also workload, availability or skills? Assumed the role only. | A3, TC-81-04 |
| Q4 | ~~Leads cannot use the reassign function yet. Will a Lead reassignment story extend it?~~ **Resolved by SCRUM-82 (17 Oct 2026):** the reassign function is now Lead-only, so the refusal's `next_step` is usable. | A6, TC-81-09 |
