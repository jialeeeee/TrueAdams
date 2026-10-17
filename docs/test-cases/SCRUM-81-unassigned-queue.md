# SCRUM-81 — Submitted Event Requests Wait in the Lead's Unassigned Queue: Test Cases

Part of SCRUM-81, continuing the numbering of [SCRUM-81-lead-assigns-coordinator.md](SCRUM-81-lead-assigns-coordinator.md): AC6–AC10, A9–A15, Q5–Q9 and TC-81-23 onwards.

**User story (derived from Week 7 customer change 5; to be confirmed):** As an Event Coordinator Lead, I want newly submitted event requests to wait in an unassigned queue that I can view, so that I can review each one and assign a suitable coordinator.

**Created:** 17 Oct 2026 · **Status of all cases:** Automated cases pass (17 Oct 2026, local Postgres + Vitest; Supabase run pending). · **Automated tests:** `backend/tests/test_unassigned_queue.py`, `backend/tests/test_event_submission.py` (TC-28-09/10, updated), `frontend/src/pages/UnassignedQueuePage.test.jsx` · **Endpoints:** `POST /api/events/drafts/<id>/submit` (SCRUM-28, changed), `GET /api/events/queue` (new) · **Related:** SCRUM-81 (assigning a waiting event), SCRUM-83 (the Lead's assigned events), SCRUM-28/29 (submission), SCRUM-55 (review)

## Acceptance criteria

The customer gave this change as a description, not as criteria. These are the team's reading of it and need confirming.

| ID | Criterion |
|----|-----------|
| AC6 | A newly submitted event request is not assigned to a coordinator; it enters the unassigned queue. |
| AC7 | The Lead can view the queue, with each waiting event's basic information, and open an event to assign it. |
| AC8 | Only the Lead can view the queue. Anyone else is denied and sees no event data. |
| AC9 | An empty queue says so. If the queue cannot be loaded, the user is told and no partial list is shown. |
| AC10 | Once a coordinator is assigned, the event leaves the queue. |

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A9 — Submission:** submitting a complete draft makes it `submitted` with no coordinator (`coordinator_id`, `coordinator_assigned_at` and `coordinator_assigned_by_id` stay empty). The SCRUM-28 rule that assigned the lowest-ID coordinator, and its refusal when no coordinator was available, are withdrawn: a submission no longer depends on coordinators. Events submitted before this change keep their coordinator. *(Q5)*
- **A10 — The queue:** the events waiting for a coordinator: status `submitted` and no coordinator. This is the same rule SCRUM-81 uses to allow an assignment (`_waiting_for_assignment`), so every listed event can be assigned. *(Q6)*
- **A11 — One shared queue:** every Lead sees the whole queue. *(Q7)*
- **A12 — Basic information:** name, proposed date (start, Singapore time, as recorded), organiser email and when it was submitted (naive UTC, shown in local time). A blank name or a missing date is sent as `null` and shown as "Not recorded". *(Q8)*
- **A13 — Order:** oldest submission first, so nothing waits unseen; requests with no submission time (older data) last; ties by event ID. *(Q9)*
- **A14 — Opening an event:** each name links to the SCRUM-81 assignment page (`/events/<id>/assign`).
- **A15 — Failures:** HTTP 503 with `retryable: true` and no list; the page shows the message with a Retry button.

## Endpoint under test

- `GET /api/events/queue` → **200** `{"events": [event, ...], "message": str | null}`.
  - event = `{"id", "title", "start_time", "status", "organiser": {"id", "email"}, "submitted_at"}`; `title`, `start_time` and `submitted_at` are `null` when not recorded.
  - `message` is the empty-queue text when `events` is empty, otherwise `null`.
- **401** without a valid session; **403** for anyone who is not a Lead; **503** `{"error", "retryable": true}` if loading fails.

## Seed data (UQ-SEED)

Users come from `backend/tests/seed_data.py` (`USERS` and `LEADS`). The real queue may hold other events, so tests assert only about their own rows, and hide real ones for the empty state.

| Ref | Title | Status | Coordinator | Organiser | Submitted (UTC) | Proposed date (start) |
|-----|-------|--------|-------------|-----------|-----------------|-----------------------|
| W1 | Harbour Lights Festival | submitted | *none* | dana | 10 Oct 2026 09:00 | 12 Dec 2026 17:00 |
| W2 | Alumni Mixer | submitted | *none* | evan | 8 Oct 2026 14:00 | 20 Nov 2026 18:30 |
| W3 | *(spaces only)* | submitted | *none* | dana | 12 Oct 2026 08:00 | *not recorded* |
| W4 | Legacy Forum | submitted | *none* | evan | *not recorded* | 25 Nov 2026 09:00 |
| H1 | Product Launch | submitted | ben | evan | 1 Oct 2026 10:00 | 20 Nov 2026 14:00 |
| U1 | Charity Fun Run | under_review | *none* | dana | 2 Oct 2026 10:00 | 5 Nov 2026 07:00 |
| D1 | Draft Workshop | draft | *none* | dana | — | 15 Jan 2027 10:00 |
| C1 | Cancelled Meetup | cancelled | *none* | dana | 3 Oct 2026 10:00 | 30 Oct 2026 19:00 |
| R1 | Startup Expo | rejected | *none* | evan | 4 Oct 2026 10:00 | 15 Nov 2026 10:00 |

---

## AC6 — Submissions enter the queue

**TC-81-23 · A submitted request has no coordinator and is in the queue**
- **Traces to:** AC6 · **Type:** Happy path
- **Steps:** As dana, submit a complete draft; as lena, load the queue.
- **Expected result:** HTTP 200 and status `submitted`; the event has no coordinator, assignment time or assigner; it is in the queue.
- **Automated:** `test_a_submitted_request_waits_in_the_queue_without_a_coordinator`; `test_event_submission.py` · `test_submission_leaves_the_request_unassigned_and_preserves_access_boundaries` (TC-28-09, updated)

**TC-81-24 · Submission no longer needs an available coordinator**
- **Traces to:** AC6 · **Type:** Boundary · **Depends on:** Q5
- **Preconditions:** No user has the coordinator role.
- **Expected result:** Submission succeeds (HTTP 200, `submitted`), where SCRUM-28 used to refuse it with HTTP 503.
- **Automated:** `test_event_submission.py` · `test_submission_does_not_need_an_available_coordinator` (TC-28-10, updated)

## AC7 — Viewing the queue

**TC-81-25 · The Lead sees each waiting event's basic information**
- **Traces to:** AC7 · **Type:** Happy path · **Depends on:** Q7, Q8
- **Steps:** Load the queue as lena, then as liam.
- **Expected result:** HTTP 200 for both, each listing W1–W4. W1 is `{"id", "title": "Harbour Lights Festival", "start_time": "2026-12-12T17:00:00", "status": "submitted", "organiser": {"id", "email"} of dana, "submitted_at": "2026-10-10T09:00:00"}`. `message` is `null`.
- **Automated:** `test_lead_sees_each_waiting_event_with_basic_information`

**TC-81-26 · Only waiting events are listed**
- **Traces to:** AC7 · **Type:** Boundary · **Depends on:** Q6
- **Expected result:** H1 (has a coordinator), U1 (under review), D1 (draft), C1 (cancelled) and R1 (rejected) are not listed.
- **Automated:** `test_only_events_waiting_for_a_coordinator_are_listed`

**TC-81-27 · Oldest submission first, unknown last**
- **Traces to:** AC7 · **Type:** Happy path · **Depends on:** Q9
- **Expected result:** W2, W1, W3, W4.
- **Automated:** `test_oldest_submission_is_listed_first`

**TC-81-28 · Missing name and date are sent as not recorded**
- **Traces to:** AC7 · **Type:** Boundary
- **Expected result:** W3 is listed with `title: null` and `start_time: null`; W4 with `submitted_at: null`.
- **Automated:** `test_missing_values_are_null`

**TC-81-29 · Every listed event can be opened for assignment**
- **Traces to:** AC7 · **Type:** Happy path
- **Steps:** For each of W1–W4, load the SCRUM-81 assignment endpoint as lena.
- **Expected result:** HTTP 200 for each.
- **Automated:** `test_every_listed_event_can_be_opened_for_assignment`

## AC8 — Only the Lead

**TC-81-30 · Every other role is denied and sees no event data**
- **Traces to:** AC8 · **Type:** Negative (authorisation)
- **Steps:** Load the queue as admin, alice, dana, farah, gus and hana.
- **Expected result:** HTTP 403 with no `events` and no event title.
- **Automated:** `test_only_leads_can_view_the_queue`

**TC-81-31 · A valid session is required, and role changes apply at once**
- **Traces to:** AC8 · **Type:** Negative (authorisation)
- **Steps:** Load with no token, an expired token and a deleted Lead's token; then as lena after her role is changed to coordinator, with her earlier token.
- **Expected result:** HTTP 401 for the session cases; HTTP 403 for lena.
- **Automated:** `test_a_valid_session_and_the_lead_role_are_required`

## AC9 — Empty and failed loads

**TC-81-32 · An empty queue says so**
- **Traces to:** AC9 · **Type:** Empty state
- **Preconditions:** Every waiting event, real ones included, is moved out of the queue inside the test's transaction.
- **Expected result:** `events` is empty and `message` is a non-empty sentence.
- **Automated:** `test_empty_queue_gets_a_message`

**TC-81-33 · Loading fails**
- **Traces to:** AC9 · **Type:** Negative (failure)
- **Preconditions:** Every database query raises `SQLAlchemyError`.
- **Expected result:** HTTP 503 with `retryable: true`, a message saying the queue could not be loaded and to try again, and no `events` or event titles. Loading again with the database working succeeds.
- **Automated:** `test_load_failure_is_reported_without_a_list_and_retry_works`

## AC10 — Leaving the queue

**TC-81-34 · An assigned event leaves the queue**
- **Traces to:** AC10 · **Type:** Happy path
- **Steps:** As lena, assign alice to W1 through SCRUM-81; load the queue.
- **Expected result:** W1 is no longer listed; W2–W4 still are.
- **Automated:** `test_an_assigned_event_leaves_the_queue`

## Frontend

**TC-81-35 · The queue shows each event's basic information**
- **Traces to:** AC7 · **Type:** Frontend
- **Expected result:** The page "Waiting events" lists each event, in the order received, with its name, "Organiser: <email>", "Proposed date: <as recorded>" and "Submitted: <local time>". A missing name, date or submission time shows "Not recorded".
- **Automated:** `UnassignedQueuePage.test.jsx`

**TC-81-36 · Each name opens the assignment page**
- **Traces to:** AC7 · **Type:** Frontend
- **Expected result:** Each name links to `/events/<id>/assign`, including an event with no name ("Not recorded").
- **Automated:** `UnassignedQueuePage.test.jsx`

**TC-81-37 · Empty queue, denial and load failure**
- **Traces to:** AC8, AC9 · **Type:** Frontend
- **Expected result:** An empty queue shows the server's message and no list. A 403 shows its message with no list and no Retry button. A failure shows the error (or a fallback for a network failure) with a Retry button and no list; retrying loads the queue.
- **Automated:** `UnassignedQueuePage.test.jsx`

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC6 | 23, 24 |
| AC7 | 25, 26, 27, 28, 29, 35, 36 |
| AC8 | 30, 31, 37 |
| AC9 | 32, 33, 37 |
| AC10 | 34 |

| Type | Test cases |
|------|-----------|
| Happy path | 23, 25, 27, 29, 34 |
| Negative | 30, 31, 33 |
| Boundary | 24, 26, 28 |
| Empty state | 32 |
| Frontend | 35, 36, 37 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q5 | Should requests submitted before this change, which already have a coordinator, stay with them? Assumed yes: only new submissions enter the queue. | A9, TC-81-23, TC-81-24 |
| Q6 | Which events belong in the queue: only submitted requests with no coordinator, or also events whose coordinator was removed later? Assumed submitted and unassigned. | A10, TC-81-26 |
| Q7 | Is there one queue for all Leads, or does each Lead have their own area? Assumed one shared queue. | A11, TC-81-25 |
| Q8 | What "basic event information" does the Lead need to choose a coordinator (e.g. expected attendance, purpose)? Assumed name, date, organiser and submission time. | A12, TC-81-25 |
| Q9 | What order is most useful: oldest submission first, soonest event date first, or something else? Assumed oldest submission first. | A13, TC-81-27 |
