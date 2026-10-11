# SCRUM-62 — Identify My Managed Events: Test Cases

**User story:** As an Event Coordinator, I want a list of the events I manage, with each event's status, so that I can quickly find the event I need and see what stage it is at.

**Created:** 11 Oct 2026 · **Status of all cases:** Automated cases pass (11 Oct 2026, Supabase + Vitest). · **Automated tests:** `backend/tests/test_managed_events.py`, `frontend/src/pages/ManagedEventsPage.test.jsx`, `frontend/src/pages/EventPlanningPage.test.jsx` · **Endpoints:** `GET /api/events/managed` (new), `GET /api/events/<id>/planning` (SCRUM-34) · **Related:** SCRUM-34 (planning view), SCRUM-33 (coordinator assignment)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The coordinator can view a list of the events assigned to them, showing each event's name, proposed date and status. |
| AC2 | Opening an event from the list shows its planning information. |
| AC3 | The event's planning view shows its current status and assigned coordinator. |
| AC4 | If the coordinator has no assigned events, an empty-state message is shown. |
| AC5 | Planning fields with no recorded value are shown as "Not recorded" rather than left blank. |

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Whose events:** the events whose current coordinator (`Event.coordinator_id`) is the caller, and only while the caller's role is `coordinator`, read from the database on every request. This is the same rule as the SCRUM-34 planning view, so every listed event can be opened. Anyone else gets HTTP 403. *(Q1)*
- **A2 — Which statuses:** every event assigned to the coordinator, whatever its status, including `cancelled` (SCRUM-34 A6 keeps cancelled events viewable). *(Q2)*
- **A3 — Proposed date:** the event's start date and time (`start_time`), Singapore time, shown exactly as recorded.
- **A4 — Order:** soonest proposed date first; events with no proposed date last; ties by event ID. *(Q3)*
- **A5 — Not recorded:** a blank name or a missing proposed date is sent as `null` and shown as "Not recorded", never as a blank. The same applies to every field on the planning view (SCRUM-34 A4), where "No" for registration required is a recorded answer.
- **A6 — Opening an event:** each listed event's name links to its planning page (`/events/<id>/planning`), which shows the SCRUM-34 planning information, including its status and coordinator.
- **A7 — Load failure:** as elsewhere, HTTP 503 with `retryable: true`; the page shows the message with a Retry button.

## Endpoint under test

- `GET /api/events/managed` → **200** `{"events": [event, ...], "message": str | null}`.
  - event = `{"id", "title", "start_time", "status"}`; `title` and `start_time` are `null` when not recorded.
  - `message` is the empty-state text when the list is empty, otherwise `null`.
- **401** without a valid session; **403** for anyone who is not a coordinator; **503** `{"error", "retryable": true}` if loading fails.

## Seed data (ME-SEED)

Users come from `backend/tests/seed_data.py`. Times are Singapore time.

| Ref | Title | Coordinator | Status | Proposed date (start) |
|-----|-------|-------------|--------|-----------------------|
| M1 | Harbour Lights Festival | alice | submitted | 12 Dec 2026 17:00 |
| M2 | Alumni Mixer | alice | approved | 20 Nov 2026 18:30 |
| M3 | Winter Networking Night | alice | cancelled | 1 Oct 2026 09:00 |
| M4 | *(spaces only)* | alice | under_review | *not recorded* |
| M5 | Product Launch | ben | submitted | 20 Nov 2026 14:00 |
| M6 | Tech Summit 2026 | *none* | submitted | 10 Nov 2026 09:00 |

chloe is a coordinator with no events.

---

## AC1 — The coordinator's list

**TC-62-01 · The coordinator sees the events assigned to them**
- **Traces to:** AC1 · **Type:** Happy path
- **Steps:** As alice, load the list.
- **Expected result:** HTTP 200. `events` holds M1–M4 and nothing coordinated by anyone else (M5) or by no one (M6). `message` is `null`.
- **Automated:** `test_coordinator_sees_only_the_events_assigned_to_them`

**TC-62-02 · Each event shows its name, proposed date and status**
- **Traces to:** AC1 · **Type:** Happy path
- **Expected result:** M1 is `{"id", "title": "Harbour Lights Festival", "start_time": "2026-12-12T17:00:00", "status": "submitted"}`. Each event shows its own status, cancelled included (M3).
- **Automated:** `test_each_event_shows_its_name_proposed_date_and_status`

**TC-62-03 · Soonest proposed date first, undated last**
- **Traces to:** AC1 · **Type:** Happy path · **Depends on:** Q3
- **Expected result:** M3, M2, M1, M4.
- **Automated:** `test_events_are_listed_soonest_first_with_undated_last`

**TC-62-04 · Reassignment moves the event between lists immediately**
- **Traces to:** AC1 · **Type:** Boundary
- **Steps:** Reassign M1 from alice to ben through the SCRUM-33 endpoint, then load both lists with tokens issued earlier.
- **Expected result:** M1 is no longer in alice's list and is in ben's.
- **Automated:** `test_reassignment_moves_the_event_to_the_new_coordinators_list`

**TC-62-05 · Only coordinators, with a valid session**
- **Traces to:** AC1 · **Type:** Negative (authorisation) · **Depends on:** Q1
- **Steps:** Load the list as admin, dana, farah, gus and hana; then with no token, an expired token and a deleted user's token; then as alice after her role is changed to organiser (using her earlier token).
- **Expected result:** HTTP 403 for the other roles and for alice after the role change; HTTP 401 for the session cases. No event details are returned.
- **Automated:** `test_only_coordinators_with_a_valid_session`

## AC2 and AC3 — Opening an event shows its planning information, status and coordinator

**TC-62-06 · A listed event opens with its planning information**
- **Traces to:** AC2, AC3 · **Type:** Happy path
- **Steps:** Take M2's ID from alice's list and open it through the SCRUM-34 planning endpoint.
- **Expected result:** HTTP 200 with title "Alumni Mixer", status `approved` and coordinator alice.
- **Automated:** `test_a_listed_event_opens_with_its_status_and_coordinator`

**TC-62-07 · Every listed event can be opened**
- **Traces to:** AC2 · **Type:** Happy path
- **Steps:** Open every event in alice's list through the planning endpoint.
- **Expected result:** HTTP 200 for each, including the cancelled M3.
- **Automated:** `test_every_listed_event_can_be_opened`

## AC4 — Empty state

**TC-62-08 · A coordinator with no events**
- **Traces to:** AC4 · **Type:** Empty state
- **Steps:** Load the list as chloe.
- **Expected result:** `events` is empty and `message` is a non-empty sentence.
- **Automated:** `test_coordinator_with_no_events_gets_an_empty_state_message`

## AC5 — Not recorded

**TC-62-09 · Missing name and date are sent as not recorded**
- **Traces to:** AC5 · **Type:** Boundary
- **Expected result:** M4 is listed (not left out) with `title: null` and `start_time: null`.
- **Automated:** `test_blank_name_and_missing_date_are_null`

## Loading fails

**TC-62-10 · The coordinator is told and can retry**
- **Traces to:** A7 · **Type:** Negative (failure)
- **Preconditions:** Every database query raises `SQLAlchemyError`.
- **Expected result:** HTTP 503 with `retryable: true` and a message saying the events could not be loaded and to try again. Loading again with the database working succeeds.
- **Automated:** `test_load_failure_is_reported_and_retry_works`

## Frontend

**TC-62-11 · The list shows name, proposed date and status**
- **Traces to:** AC1 · **Type:** Frontend
- **Expected result:** The page "My managed events" lists each event with its name, "Proposed date: <date and time as recorded>" and "Status: <label>".
- **Automated:** `ManagedEventsPage.test.jsx`

**TC-62-12 · Each name opens the event's planning page**
- **Traces to:** AC2 · **Type:** Frontend
- **Expected result:** Each name links to `/events/<id>/planning`. An event with no name is still linked, as "Not recorded".
- **Automated:** `ManagedEventsPage.test.jsx`

**TC-62-13 · Empty state, load failure and retry on the list**
- **Traces to:** AC4, A7 · **Type:** Frontend
- **Expected result:** With no events, the server's message is shown and no list. On failure, the error (or a fallback for a network failure) is shown with a Retry button; retrying loads the list.
- **Automated:** `ManagedEventsPage.test.jsx`

**TC-62-14 · The planning page shows status and coordinator**
- **Traces to:** AC3 · **Type:** Frontend
- **Expected result:** The planning page shows "Status: <label>" and the coordinator's email, with every planning field labelled.
- **Automated:** `EventPlanningPage.test.jsx`

**TC-62-15 · Unrecorded planning fields say "Not recorded"**
- **Traces to:** AC5 · **Type:** Frontend
- **Expected result:** Every field that is `null` shows "Not recorded"; no field is blank. Registration required `false` shows "No".
- **Automated:** `EventPlanningPage.test.jsx`, `ManagedEventsPage.test.jsx` (missing proposed date)

**TC-62-16 · Planning page load failure**
- **Traces to:** A7 · **Type:** Frontend
- **Expected result:** A retryable failure shows the server's message with a Retry button, and retrying loads the event. A refusal (HTTP 403) shows its message with no Retry button and no event information.
- **Automated:** `EventPlanningPage.test.jsx`

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 03, 04, 05, 11 |
| AC2 | 06, 07, 12 |
| AC3 | 06, 14 |
| AC4 | 08, 13 |
| AC5 | 09, 15 |
| A7 (load failure) | 10, 13, 16 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 02, 03, 06, 07 |
| Negative | 05, 10 |
| Boundary | 04, 09 |
| Empty state | 08 |
| Cross-cutting (authorisation) | 04, 05 |
| Frontend | 11, 12, 13, 14, 15, 16 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Should admins (or a supervisor) see a list of every event and its coordinator? Assumed out of scope: only coordinators have this list. | A1, TC-62-05 |
| Q2 | Should finished, cancelled or rejected events stay in the list, be hidden, or be shown in a separate section? Assumed every assigned event is listed. | A2, TC-62-02 |
| Q3 | What order is most useful: soonest proposed date, most recently assigned, or grouped by status? Assumed soonest proposed date first. | A4, TC-62-03 |
