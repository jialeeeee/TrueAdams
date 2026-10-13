# SCRUM-61 — Request Event Coordinator Reassignment: Test Cases

**User story:** As an Event Coordinator, I want to request that another coordinator takes over an event I am assigned to, so that the event keeps a coordinator when I cannot continue.

**Created:** 13 Oct 2026 · **Status of all cases:** Written test-first (TDD, red). Nothing is implemented yet, so every automated test fails until the feature is built. · **Automated tests:** `backend/tests/test_reassignment_request.py`, `frontend/src/pages/ReassignmentRequestPage.test.jsx`, `frontend/src/pages/EventDetailsPage.test.jsx` (entry point) · **Endpoints:** `GET` and `POST /api/events/<id>/reassignment` · **Related:** SCRUM-74 (the event page carries the entry point), the existing coordinator assignment (`PUT /api/events/<id>/coordinator`), SCRUM-31 (notification and email pattern)

**Source:** the team's "Sprint 2 test cases" sheet (IS212-US61-TC1 to TC17). Case `TC-61-nn` automates sheet case `IS212-US61-TCn`. Sheet users and events map to the seed data below: coord_alice, coord_bob and coord_carol are alice, ben and chloe; attendee_dan is farah; event E-101 is E1, E-102 is E2 and E-103 is E3.

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | Only the event's current main coordinator can see and use "Request reassignment". |
| AC2 | The requester selects the new coordinator from eligible coordinators only; they cannot select themselves or an ineligible user. |
| AC3 | A reason is required (not empty, at most 500 characters); an empty or over-length reason is rejected with a clear error. |
| AC4 | A successful submission records the event, requester, selected coordinator, reason and request time, sets the status to Pending, and shows a confirmation. |
| AC5 | The selected coordinator is notified of the pending request. |
| AC6 | While the request is pending, the requester stays main coordinator, and the assignment and the event's status are unchanged. |
| AC7 | An event can have at most one pending reassignment request; a second attempt is rejected with a clear message. |
| AC8 | A request cannot be made for a cancelled, completed or past event. |
| AC9 | If no eligible coordinator is available, the user is told and no request is created. |
| AC10 | If saving fails, no request is created, the assignment is unchanged, and an error is shown. |
| AC11 | Signed-out users are sent to the sign-in page. |

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Who may request:** only a user whose stored role is `coordinator` and who is the event's `coordinator_id` (the existing `_is_current_coordinator` rule), checked in the database on every request. Everyone else gets HTTP 403, including admins and the event's organiser. *(Q1)*
- **A2 — Who is eligible:** any user whose role is `coordinator` except the requester. This is the existing `_eligible_coordinators(event)` helper, used for both the list and the submit check so the two cannot disagree. Workload and availability are not considered. *(Q2)*
- **A3 — The reason (confirmed 13 Oct 2026):** required, trimmed of surrounding spaces, at most 500 characters (`MAX_REASON_LENGTH`). Exactly 500 is accepted; 501 is rejected. The original Jira text said the reason "can" be included; the team decided it is required.
- **A4 — The request:** a new table `reassignment_requests` with the event, requester, selected coordinator, reason, `status` and `requested_at` (naive UTC, like the other audit times). The only status in this story is `pending`. Accepting or declining is a later story. *(Q3)*
- **A5 — Notification:** the selected coordinator gets an in-app `Notification` (kind `reassignment_requested`, linked to the event, naming the event and the requester) and a queued email. They are saved with the request in one commit, and the email is queued after it. A queue failure is not fatal: the response says `email_queued: false`. Nobody else is notified. *(Q4)*
- **A6 — One pending request:** a partial unique index allows one `pending` request per event. A second attempt, to any coordinator, gets HTTP 409 with reason `pending`.
- **A7 — Blocked events:** a request is refused (HTTP 409, reason `cancelled` or `past`) for a cancelled event or one that has ended, meaning its end time is at or before now (half-open: an event is past from its end time). `completed` is not a status in use, so "past" covers it. An event that has started but not ended can still be reassigned. *(Q5)*
- **A8 — Nobody eligible:** `GET` returns `can_request: false`, `blocked_reason: "no_eligible_coordinators"` and a message; `POST` returns 422. Nothing is saved.
- **A9 — What the page shows:** `GET` always returns the form data for an allowed caller, with `can_request` and `blocked_reason` (`pending`, `cancelled`, `past` or `no_eligible_coordinators`) and a human `message`. The page uses these to hide the form rather than guessing.
- **A10 — Order of checks:** not signed in (401) → unknown event (404) → not the main coordinator (403) → blocked event or existing pending request (409) → invalid body (400) → ineligible coordinator (422). The tests do not depend on the order of the last three; they never combine a blocked event with a bad body.
- **A11 — Saving fails:** HTTP 503 with `retryable: true`. A failed load is also a 503, never an empty list or an open form. No request, notification or email is created, and the assignment is unchanged.
- **A12 — Entry point and sign-in:** the event details page (SCRUM-74) shows a "Request reassignment" link only when `can_request_reassignment` is true, linking to `/events/<id>/reassign`. Pages treat an HTTP 401 as signed out and go to `/login`. *(Q6)*

## Endpoints under test

- `GET /api/events/<id>/reassignment`:
  - **200** `{"event": {"id", "title", "status"}, "coordinators": [{"id", "email"}], "pending_request": request or null, "can_request": bool, "blocked_reason": null or a reason, "message": str or null}`.
  - **401**, **403**, **404** `{"error": str}`; **503** `{"error": str, "retryable": true}`.
- `POST /api/events/<id>/reassignment` with body `{"coordinator_id": int, "reason": str}`:
  - **201** `{"message": str, "request": request, "notification": {"in_app": true, "email_queued": bool}}`.
  - **400** `{"error": str, "field": "coordinator_id" or "reason"}`; **422** `{"error": str}`; **409** `{"error": str, "reason": "pending" | "cancelled" | "past"}`.
  - **401**, **403**, **404**, **503** as above.
- A request is `{"id", "event_id", "requester_id", "coordinator_id", "reason", "status", "requested_at"}`.
- `GET /api/events/<id>` (SCRUM-74) also returns `can_request_reassignment`.

## What the implementation needs

- `ReassignmentRequest` model and `backend/db/reassignment_requests.sql`: a new table with row level security, a partial unique index `on (event_id) where status = 'pending'`, and a header comment naming this story. Add the table to **both** lists in `backend/db/test_role.sql`. The script must be run in the Supabase SQL editor as the project owner, then `test_role.sql`, before merging (until then `test_database_tables_match_the_models` fails for everyone).
- In `app/events/routes.py`: the two routes, `MAX_REASON_LENGTH = 500` and `REASSIGNMENT_NOTIFICATION = "reassignment_requested"` as named constants with comments, and `singapore_now` imported from `app.registrations.routes` so tests can patch `app.events.routes.singapore_now`.
- `frontend/src/pages/ReassignmentRequestPage.jsx` with the route `/events/:eventId/reassign` in `App.jsx`; the box must not set `maxLength`, so an over-length reason is explained rather than silently cut. `MAX_REASON_LENGTH` carries a `// Must match` comment.
- Update the C4 diagram: this adds a stored entity.

## Seed data (RR-SEED)

"Now" is fixed at **13 Oct 2026 12:00** Singapore time. Users come from `backend/tests/seed_data.py`. Every event is organised by dana and coordinated by alice, and is `confirmed` and runs 20 Nov 2026 10:00 – 12:00 unless the table says otherwise.

| Ref | Title | Differs from the defaults | Requests already made |
|-----|-------|---------------------------|-----------------------|
| E1 | Chem Open House | — | none |
| E2 | Cancelled Mixer | status `cancelled` | none |
| E3 | Past Seminar | 1 Sep 2026 10:00 – 12:00 | none |

The requester is alice and the selected coordinator is ben unless a case says otherwise. chloe is a coordinator who is not assigned to the events, and farah is an attendee. The reason is "Overseas on 20/11/2026" unless a case says otherwise.

The sheet says "approved" for E-101; the repo's published status is `confirmed`, so E1 is `confirmed`. The sheet's browser steps become API calls and component tests.

---

## AC1 — Only the main coordinator

**TC-61-01 · The main coordinator can open the request** *(sheet TC1)*
- **Traces to:** AC1 · **Type:** Happy path
- **Steps:** As alice, `GET` the reassignment form for E1, and read E1's details.
- **Expected result:** HTTP 200 with the event's id and title, `can_request: true`, no `blocked_reason` and no pending request. The event's details have `can_request_reassignment: true`.
- **Automated:** `WhoCanRequestTests.test_main_coordinator_can_open_the_request`; frontend: "offers Request reassignment to the event's main coordinator", "opens the form for the event's main coordinator".

**TC-61-02 · A coordinator who is not assigned cannot** *(sheet TC2)*
- **Traces to:** AC1 · **Type:** Negative (authorisation)
- **Steps:** As ben, then chloe (neither coordinates E1), `GET` the form, `POST` a request, and read E1's details.
- **Expected result:** HTTP 403 for both calls, `can_request_reassignment: false`, and no request saved.
- **Automated:** `WhoCanRequestTests.test_unassigned_coordinator_cannot_request`; frontend: "does not offer Request reassignment to anyone else", "shows the server's refusal when someone else is not allowed to open the form".

**TC-61-03 · Other roles cannot, and the role comes from the database** *(sheet TC3)*
- **Traces to:** AC1 · **Type:** Negative (authorisation) · **Depends on:** Q1
- **Steps:** As farah, dana, admin and gus (venue staff), `GET` and `POST`. As farah, request an event ID that does not exist. Then change alice's role to attendee and use her old token.
- **Expected result:** HTTP 403 every time for existing events (the details show `can_request_reassignment: false`), and HTTP 404 for the unknown event (404 comes before 403). Alice's old token, issued while she was a coordinator, is refused with 403. Nothing is saved.
- **Automated:** `WhoCanRequestTests.test_other_roles_cannot_request`, `test_access_follows_role_changes`.

## AC2 — Who can be selected

**TC-61-04 · The list shows only eligible coordinators** *(sheet TC4)*
- **Traces to:** AC2 · **Type:** Happy path · **Depends on:** Q2
- **Steps:** As alice, `GET` the form for E1.
- **Expected result:** `coordinators` includes ben and chloe, not alice, and no attendee, organiser, admin or staff user. Each entry has only `id` and `email`.
- **Automated:** `SelectionTests.test_list_shows_only_eligible_coordinators`; frontend: "lists the eligible coordinators and not the requester".

**TC-61-05 · Tampering: yourself, an ineligible user, an unknown user, a bad ID** *(sheet TC5)*
- **Traces to:** AC2 · **Type:** Negative (authorisation) · **Depends on:** Q2
- **Steps:** As alice, `POST` with `coordinator_id` set to alice, to farah (attendee), to dana (organiser) and to an ID no user has. Then send `coordinator_id` as missing, `null`, `"2"`, `true`, `1.5`, a list and an object.
- **Expected result:** HTTP 422 for the first four, with a plain message and no stack trace; HTTP 400 with `field: "coordinator_id"` for the rest. No request or notification is created.
- **Automated:** `SelectionTests.test_requester_cannot_select_themselves_or_an_ineligible_user`, `test_coordinator_must_be_an_integer`; frontend: "blocks a request with no coordinator selected".

## AC3 — The reason

**TC-61-06 · A reason at the maximum length is accepted** *(sheet TC6)*
- **Traces to:** AC3 · **Type:** Boundary
- **Steps:** As alice, `POST` a reason of 500 characters.
- **Expected result:** HTTP 201, and the 500-character reason is saved.
- **Automated:** `ReasonTests.test_reason_at_the_maximum_length_is_accepted`; frontend: "accepts a reason of exactly the maximum length".

**TC-61-07 · A reason over the maximum length is rejected** *(sheet TC7)*
- **Traces to:** AC3 · **Type:** Boundary
- **Steps:** As alice, `POST` a reason of 501 characters.
- **Expected result:** HTTP 400 with `field: "reason"` and a message that gives the limit (500). No request or notification. The page shows the same limit and sends nothing, and keeps the typed text.
- **Automated:** `ReasonTests.test_reason_over_the_maximum_length_is_rejected`; frontend: "blocks a reason over the maximum length and says so".

**TC-61-08 · A missing or blank reason is rejected** *(sheet TC8)*
- **Traces to:** AC3 · **Type:** Negative
- **Steps:** As alice, `POST` with the reason missing, `null`, empty, only spaces or tabs, and a number. Then send a body that is not JSON and a JSON list.
- **Expected result:** HTTP 400 with `field: "reason"` and a message that says a reason is needed (for the first five), and HTTP 400 for the bad bodies. Nothing is saved. The page blocks an empty or spaces-only reason with "Enter a reason for the reassignment." and sends nothing.
- **Automated:** `ReasonTests.test_reason_is_required`, `test_body_must_be_a_json_object`; frontend: "blocks an empty reason (nothing)", "blocks an empty reason (only spaces)".

## AC4, AC5, AC6 — What a request does

**TC-61-09 · A successful request is recorded as Pending** *(sheet TC9)*
- **Traces to:** AC4 · **Type:** Happy path
- **Steps:** As alice, `POST` ben and the reason for E1. Then `POST` a reason with spaces around it.
- **Expected result:** HTTP 201 with a confirmation message. The request has the event, requester (alice), selected coordinator (ben), the reason, status `pending` and a `requested_at` time that is naive UTC and falls between just before and just after the call. The saved row matches. Surrounding spaces are not saved. The page sends the selected coordinator and reason, shows the confirmation and "Status: Pending", and removes the form; Submit is disabled while sending, so a double click sends one request.
- **Automated:** `SubmitTests.test_submission_is_recorded_as_pending`, `test_reason_is_trimmed`; frontend: "sends the selected coordinator and the reason, then confirms and shows the request as pending", "sends one request when Submit is clicked twice".

**TC-61-10 · Only the selected coordinator is notified** *(sheet TC10)*
- **Traces to:** AC5 · **Type:** Happy path · **Depends on:** Q4
- **Steps:** As alice, `POST` ben for E1. Then repeat with the email queue raising an error.
- **Expected result:** One in-app notification of kind `reassignment_requested` for ben about E1, naming "Chem Open House" and alice's email, and none for alice or chloe. One email queued to ben's address. The response says `in_app: true, email_queued: true`. With the queue down, the response is still 201, says `email_queued: false`, and the request and notification are saved.
- **Automated:** `SubmitTests.test_selected_coordinator_is_notified`, `test_email_queue_failure_is_not_fatal`.

**TC-61-11 · Nothing changes while the request is pending** *(sheet TC11)*
- **Traces to:** AC6 · **Type:** Happy path
- **Steps:** As alice, `POST` a request for E1. Read E1's coordinator and status, then `GET` the form.
- **Expected result:** The coordinator is still alice (`GET /api/events/<id>/coordinator` agrees), the assignment time and the event's status are unchanged. The form shows the pending request (`status: "pending"`, to ben), `can_request: false`, `blocked_reason: "pending"` and a message about the pending request. The page shows "Status: Pending" and no form.
- **Automated:** `SubmitTests.test_assignment_and_status_do_not_change_while_pending`, `test_requester_sees_the_pending_request`; frontend: "shows an existing request as pending and offers no second request".

## AC7, AC8, AC9 — Refused requests

**TC-61-12 · A second pending request is rejected** *(sheet TC12)*
- **Traces to:** AC7 · **Type:** Negative (business rule)
- **Steps:** With a pending request from alice to ben on E1, `POST` a request for chloe. Then, on another event alice coordinates, `POST` a request.
- **Expected result:** The first gets HTTP 409, reason `pending`, a message that mentions "pending", and nothing is saved or notified. The second gets HTTP 201: the limit is per event, not per coordinator. The page shows the server's message and keeps what was typed.
- **Automated:** `RefusedRequestTests.test_second_pending_request_is_rejected`, `test_pending_request_on_one_event_does_not_block_another`; frontend: "shows the server's message for a 409 and keeps what was typed".

**TC-61-13 · A cancelled event is blocked** *(sheet TC13)*
- **Traces to:** AC8 · **Type:** Negative · **Depends on:** Q5
- **Steps:** As alice, `GET` the form and `POST` a request for E2.
- **Expected result:** The form has `can_request: false`, `blocked_reason: "cancelled"` and a message mentioning "cancelled". The `POST` gets HTTP 409, reason `cancelled`. Nothing is saved.
- **Automated:** `RefusedRequestTests.test_cancelled_event_is_blocked`; frontend: "explains why a cancelled event cannot be reassigned".

**TC-61-14 · A past event is blocked** *(sheet TC14)*
- **Traces to:** AC8 · **Type:** Negative, boundary · **Depends on:** Q5
- **Steps:** As alice, `GET` the form and `POST` a request for E3 (ended 1 Sep 2026). Then, with now = 12:00, `POST` for an event ending at 12:01 and for one ending at exactly 12:00.
- **Expected result:** E3 gives `blocked_reason: "past"` and a message, and HTTP 409, reason `past`. The event ending at 12:01 is accepted (HTTP 201). The event ending at 12:00 is refused (HTTP 409, `past`): an event is past from its end time.
- **Automated:** `RefusedRequestTests.test_past_event_is_blocked`, `test_event_is_past_from_its_end_time`; frontend: "explains why a past event cannot be reassigned".

**TC-61-15 · No eligible coordinator is available** *(sheet TC15)*
- **Traces to:** AC9 · **Type:** Negative
- **Preconditions:** The shared eligibility rule returns nobody. Real coordinators may already exist in the database and cannot be removed by a test, so the test makes `_eligible_coordinators` return an empty list.
- **Steps:** As alice, `GET` the form and `POST` ben.
- **Expected result:** `coordinators` is empty, `can_request: false`, `blocked_reason: "no_eligible_coordinators"` and a message saying no eligible coordinator is available. The `POST` gets HTTP 422. Nothing is saved or notified. The page shows the message and no form.
- **Automated:** `RefusedRequestTests.test_no_eligible_coordinator`; frontend: "says no eligible coordinator is available and offers no way to submit".

## AC10 — Saving fails

**TC-61-16 · Save failure leaves everything unchanged** *(sheet TC16)*
- **Traces to:** AC10 · **Type:** Negative (failure)
- **Preconditions:** The commit raises `SQLAlchemyError`. In a second test, loading the user raises it.
- **Steps:** As alice, `POST` ben for E1. Then retry with the database working. Separately, `GET` the form while loads fail.
- **Expected result:** HTTP 503 with `retryable: true`, saying the request was not saved and to try again, without the database error. No request, no notification, no email; alice is still the coordinator. The retry gives HTTP 201. A failed load is a 503 with `retryable: true`. The page shows the server's message, keeps what was typed, leaves Submit enabled and succeeds on the second try; a network failure shows a fallback message; a form that could not be loaded offers Retry.
- **Automated:** `SaveFailureTests.test_failed_save_changes_nothing`, `test_failed_load_is_reported_as_a_failure`; frontend: "shows an error when saving fails and lets the coordinator try again without retyping", "shows a fallback message when the server cannot be reached", "shows why the form could not be loaded and lets the coordinator try again".

## AC11 — Signed out

**TC-61-17 · Signed-out users are sent to sign in** *(sheet TC17)*
- **Traces to:** AC11 · **Type:** Negative (authentication)
- **Steps:** `GET` and `POST` with no token, an expired token and the token of a deleted user.
- **Expected result:** HTTP 401 every time, and nothing about the event in the body. Nothing is saved. The page goes to `/login` and shows no event or form.
- **Automated:** `SignedOutTests.test_signed_out_users_get_401`; frontend: "sends a signed-out user to the sign-in page and shows no event or form".

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 03 |
| AC2 | 04, 05 |
| AC3 | 06, 07, 08 |
| AC4 | 09 |
| AC5 | 10 |
| AC6 | 11 |
| AC7 | 12 |
| AC8 | 13, 14 |
| AC9 | 15 |
| AC10 | 16 |
| AC11 | 17 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 04, 09, 10, 11 |
| Negative | 02, 03, 05, 08, 12, 13, 14, 15, 16, 17 |
| Boundary | 06, 07, 14 |
| Cross-cutting (authorisation) | 02, 03, 05 |
| Cross-cutting (authentication) | 17 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Can admins (or the event's organiser) also request a reassignment, or only the main coordinator? Assumed: only the main coordinator. | A1, TC-61-03 |
| Q2 | Who counts as an eligible coordinator? Should it exclude coordinators who are on leave, already over a workload limit, or in a different team? Assumed: any coordinator except the requester. | A2, TC-61-04, 05, 15 |
| Q3 | Who accepts or declines the request, and what happens then? There is no story for it yet, so a request stays Pending. Does the main coordinator remain responsible until it is accepted? Assumed: yes. | A4, TC-61-11 |
| Q4 | How is the selected coordinator notified: in the app, by email or both? Assumed: both. | A5, TC-61-10 |
| Q5 | Which event statuses block a request? The story says cancelled, completed or past. Assumed: `cancelled` and "has ended"; there is no `completed` status in use. | A7, TC-61-13, 14 |
| Q6 | Where should coordinators find "Request reassignment": on the event page (assumed), or in My managed events? | A12 |
