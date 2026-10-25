# SCRUM-72 — Event Coordinator Views Registration Information: Test Cases

**User story:** As an Event Coordinator, I want to view registration information for the events I coordinate so that I can plan venue and logistics arrangements around the expected attendance.

**Created:** 25 Oct 2026 · **Status of all cases:** Automated cases pass (25 Oct 2026, Supabase + Vitest). · **Automated tests:** `backend/tests/test_coordinator_registrations.py`, `frontend/src/pages/ManagedRegistrationsPage.test.jsx`, `frontend/src/pages/RegistrationOverviewPage.test.jsx` · **Endpoints:** `GET /api/events/managed/registrations` (new), `GET /api/events/<id>/registration-overview` (new) · **Related:** SCRUM-62 (the coordinator's managed events; the same events are listed here), SCRUM-54 (the organiser's view of the same registrations, with attendee details), SCRUM-45 (places and registration period), SCRUM-68 (withdrawing), SCRUM-82 (a Lead reassigns an event)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The Event Coordinator can see a list of the events assigned to them, each with its registration summary (e.g. total registrations and capacity). |
| AC2 | The Event Coordinator can open an assigned event to see the registration details needed for coordination. |
| AC3 | Only events assigned to the Event Coordinator are shown. Registration information for other events is not visible. |
| AC4 | If the Event Coordinator tries to access registration information for an event not assigned to them, access is denied and a message is displayed. |
| AC5 | If an event has no registrations, the system shows that there are none. |
| AC6 | If the registration information cannot be retrieved, an error is displayed and no partial or incorrect data is shown. |

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Whose events:** a coordinator's events are those whose current coordinator (`Event.coordinator_id`) they are, while their role is `coordinator`, read from the database on every request. This is SCRUM-62's rule (`is_current_coordinator`), so the events listed here are the ones in "My managed events", and a reassignment moves an event between lists immediately. Everyone else, including a Coordinator Lead, an admin and the event's organiser, gets HTTP 403. *(Q1)*
- **A2 — Which events are listed:** every assigned event, whatever its status, as SCRUM-62 A2. Events that have not set up registration are listed with capacity and remaining places "Not set up". *(Q2)*
- **A3 — Total registrations:** the number of `registered` registrations, the places taken, as SCRUM-54 A3. Remaining places are capacity minus that, never below 0; with no capacity, both are `null`.
- **A4 — Details needed for coordination:** the figures for planning the venue and logistics: registrations by status (registered, withdrawn, cancelled), capacity and remaining places, the registration period, the organiser's expected attendance, and the venue with its capacity. **Attendees' identities are not included**: the story asks only for what coordination needs, and SCRUM-54 shows attendee details to the event's organiser alone. *(Q3)*
- **A5 — No registrations:** an event with no registrations of any status gets a message saying there are none, with its figures (all 0) still shown. An event whose attendees all withdrew shows the withdrawn count instead.
- **A6 — Order:** soonest proposed date first, undated last, ties by event ID, as SCRUM-62 A4.
- **A7 — Refusal:** an event that does not exist is HTTP 404; an event not assigned to the caller is HTTP 403 with a message saying so and nothing about the event. Checked 401 → 404 → 403, as AGENTS.md requires.
- **A8 — Load failure:** HTTP 503 with `retryable: true` and no event or registration data, even if part of it had loaded. The page shows the message with a Retry button and no data, and ignores a late reply for an event it has moved away from.

## Endpoints under test

- `GET /api/events/managed/registrations` → **200** `{"events": [event, ...], "message": str | null}`.
  - event = `{"id", "title", "start_time", "status", "registration": {"capacity", "registered_count", "slots_remaining"}}`, as SCRUM-54's list.
  - **401** without a valid session; **403** for anyone who is not a coordinator; **503** `{"error", "retryable": true}` if loading fails.
- `GET /api/events/<id>/registration-overview` → **200** `{"event": event, "registration": overview, "message": str | null}`.
  - event = `{"id", "title", "start_time", "end_time", "status", "expected_attendance", "venue": {"name", "capacity"} | null}`.
  - overview = `{"capacity", "registered_count", "slots_remaining", "withdrawn_count", "cancelled_count", "opens_at", "closes_at"}`; times are Singapore time as recorded, `null` when not set up.
  - `message` is the empty-state text when the event has no registrations, otherwise `null`.
  - **401** without a valid session; **404** for an unknown event; **403** for an event not assigned to the caller; **503** `{"error", "retryable": true}` if loading fails.

## Seed data (CR-SEED)

Users come from `backend/tests/seed_data.py` (`USERS` and `LEADS`), plus three attendees made for the test (`att1`–`att3`). Event times are Singapore time; registration times are UTC. The venue Harbour Hall holds 120 people.

| Ref | Title | Coordinator | Status | Proposed date (start) | Expected attendance | Venue | Places | Registration period |
|-----|-------|-------------|--------|-----------------------|---------------------|-------|--------|---------------------|
| C1 | Alumni Mixer | alice | approved | 20 Nov 2026 18:30 | 60 | Harbour Hall | 50 | 1 Oct 2026 09:00 – 15 Nov 2026 18:00 |
| C2 | Harbour Lights Festival | alice | approved | 12 Dec 2026 17:00 | 2 | *none* | 2 | 1 Oct 2026 09:00 – 10 Dec 2026 18:00 |
| C3 | Winter Networking Night | alice | submitted | 1 Nov 2026 09:00 | *not recorded* | *none* | *not set up* | *not set up* |
| C4 | Product Launch | ben | approved | 20 Nov 2026 14:00 | 30 | *none* | 30 | 1 Oct 2026 09:00 – 18 Nov 2026 18:00 |
| C5 | Tech Summit 2026 | *none* | submitted | 10 Nov 2026 09:00 | 100 | *none* | *not set up* | *not set up* |

All events are organised by dana.

| Ref | Event | Attendee | Status |
|-----|-------|----------|--------|
| G1 | C1 | att1 | registered |
| G2 | C1 | farah | registered |
| G3 | C1 | att2 | withdrawn |
| G4 | C1 | att3 | cancelled |
| G5 | C2 | att1 | registered |
| G6 | C2 | att3 | registered |
| G7 | C4 | att2 | registered |

C3 has no registrations. chloe is a coordinator with no events.

---

## AC1 — The coordinator's events with their registration summary

**TC-72-01 · The coordinator sees the events assigned to them**
- **Traces to:** AC1, AC3 · **Type:** Happy path · **Depends on:** Q1, Q2
- **Steps:** As alice, load `GET /api/events/managed/registrations`.
- **Expected result:** HTTP 200. `events` holds C1, C2 and C3; not ben's C4 or the unassigned C5. `message` is `null`.
- **Automated:** `test_coordinator_sees_only_the_events_assigned_to_them`

**TC-72-02 · Each event shows its registration summary**
- **Traces to:** AC1 · **Type:** Happy path
- **Expected result:** C1 has capacity 50, 2 registered (the withdrawn G3 and cancelled G4 are not counted) and 48 remaining. C2 has capacity 2, 2 registered and 0 remaining. C3 has capacity `null`, 0 registered and remaining `null`. Each also has its name, proposed date and status.
- **Automated:** `test_each_event_shows_its_registration_summary`

**TC-72-03 · Soonest proposed date first**
- **Traces to:** AC1 · **Type:** Happy path
- **Expected result:** C3, C1, C2.
- **Automated:** `test_events_are_listed_soonest_first`

## AC2 — The registration details needed for coordination

**TC-72-04 · Opening an event shows its coordination figures**
- **Traces to:** AC2 · **Type:** Happy path · **Depends on:** Q3
- **Steps:** Take C1's ID from alice's list and load `GET /api/events/<id>/registration-overview`.
- **Expected result:** HTTP 200. `event` is C1 with its times, status, expected attendance 60 and venue Harbour Hall (capacity 120). `registration` has capacity 50, 2 registered, 48 remaining, 1 withdrawn, 1 cancelled, and the period `2026-10-01T09:00:00` to `2026-11-15T18:00:00`. `message` is `null`.
- **Automated:** `test_opening_an_event_shows_its_coordination_figures`

**TC-72-05 · Attendees' identities are not shown to the coordinator**
- **Traces to:** AC2 · **Type:** Negative (privacy) · **Depends on:** Q3
- **Expected result:** C1's overview contains no attendee's ID or email and no list of registrations.
- **Automated:** `test_attendee_identities_are_not_shown`

## AC3 — Only the coordinator's assigned events

**TC-72-06 · Reassignment moves the event's registration information immediately**
- **Traces to:** AC3 · **Type:** Boundary
- **Steps:** With tokens issued beforehand, a Lead (lena) reassigns C1 from alice to ben through `PUT /api/events/<id>/coordinator`. Then load both lists and C1's overview as each.
- **Expected result:** C1 is no longer in alice's list and her request for its overview is refused with 403; it is in ben's list and he can open it.
- **Automated:** `test_reassignment_moves_the_registration_information_immediately`

**TC-72-07 · Only coordinators, with a valid session, checked on every request**
- **Traces to:** AC3 · **Type:** Negative (authorisation) · **Depends on:** Q1
- **Steps:** Load the list as admin, dana, farah, gus, hana and lena; with no token, an expired token and a deleted user's token; and as alice after her role is changed to organiser (using her earlier token).
- **Expected result:** HTTP 403 for the other roles and for alice after the change; HTTP 401 for the session cases. No event details are returned.
- **Automated:** `test_only_coordinators_with_a_valid_session_have_the_list`

## AC4 — Access denied for events not assigned to the coordinator

**TC-72-08 · Another coordinator's or an unassigned event is refused with a message**
- **Traces to:** AC4 · **Type:** Negative (authorisation)
- **Steps:** As alice, load the overview of C4 (ben's) and C5 (unassigned).
- **Expected result:** HTTP 403 with a message saying she can only view registration information for events assigned to her. The response contains no event title or registration figures.
- **Automated:** `test_an_event_not_assigned_to_the_coordinator_is_refused_with_a_message`

**TC-72-09 · Other roles are refused, including the event's organiser and a Lead**
- **Traces to:** AC4 · **Type:** Negative (authorisation) · **Depends on:** Q1
- **Steps:** Load C1's overview as admin, dana (its organiser), farah, gus, hana and lena.
- **Expected result:** HTTP 403 for each, with a message and no event details.
- **Automated:** `test_other_roles_are_refused_an_events_overview`

**TC-72-10 · Unknown event and invalid session**
- **Traces to:** AC4 · **Type:** Negative
- **Steps:** Load the overview of an event ID that does not exist, as alice; load C1's overview without a token.
- **Expected result:** HTTP 404 "Event not found."; HTTP 401.
- **Automated:** `test_unknown_event_is_not_found_and_a_session_is_required`

## AC5 — No registrations

**TC-72-11 · An event with no registrations says so**
- **Traces to:** AC5 · **Type:** Empty state
- **Steps:** As alice, load C3's overview.
- **Expected result:** HTTP 200. `message` is a non-empty sentence; `event` is still C3, and every count is 0, with capacity, remaining places and the period `null`.
- **Automated:** `test_event_with_no_registrations_says_there_are_none`

**TC-72-12 · A coordinator with no events**
- **Traces to:** AC5 · **Type:** Empty state
- **Steps:** Load the list as chloe.
- **Expected result:** `events` is empty and `message` is a non-empty sentence.
- **Automated:** `test_coordinator_with_no_events_gets_an_empty_state_message`

## AC6 — Loading fails

**TC-72-13 · The list fails as a whole and can be retried**
- **Traces to:** AC6 · **Type:** Negative (failure)
- **Preconditions:** (a) every database query fails; (b) only the registration counts fail, after the events have loaded.
- **Expected result:** HTTP 503 with `retryable: true` and a message saying the information could not be loaded and to try again, with no `events` and no event titles in either case. Loading again succeeds.
- **Automated:** `test_list_load_failure_returns_no_partial_data_and_retry_works`

**TC-72-14 · The overview fails as a whole and can be retried**
- **Traces to:** AC6 · **Type:** Negative (failure)
- **Preconditions:** The event loads, then loading its registration counts fails.
- **Expected result:** HTTP 503 with `retryable: true`, a message to try again, and no `event`, `registration` or title. Loading again succeeds.
- **Automated:** `test_overview_load_failure_returns_no_partial_data_and_retry_works`

## Frontend

**TC-72-15 · The list shows each event's registration summary**
- **Traces to:** AC1 · **Type:** Frontend
- **Expected result:** The page "Registrations for my managed events" lists each event with its name, "Proposed date: …", "Status: …", "Registrations: n", "Capacity: n" and "Remaining places: n" ("Not set up" without a capacity). Each name links to `/events/<id>/registration-overview`.
- **Automated:** `ManagedRegistrationsPage.test.jsx`

**TC-72-16 · The overview shows the coordination figures**
- **Traces to:** AC2 · **Type:** Frontend
- **Expected result:** The event's name, dates, status, "Expected attendance: …" and "Venue: <name> (holds n)", then "Registrations: n", "Capacity: n", "Remaining places: n", "Withdrawn: n", "Cancelled: n" and "Registration period: <opens> to <closes>", times as recorded. Unrecorded values say "Not recorded", "No venue yet" or "Not set up".
- **Automated:** `RegistrationOverviewPage.test.jsx`

**TC-72-17 · Access denied is shown with no data and no Retry**
- **Traces to:** AC4 · **Type:** Frontend
- **Expected result:** On HTTP 403 the server's message is shown, with no event information and no Retry button.
- **Automated:** `RegistrationOverviewPage.test.jsx`

**TC-72-18 · Empty states**
- **Traces to:** AC5 · **Type:** Frontend
- **Expected result:** With no registrations, the server's message is shown with the event's figures. With no events, the list page shows the server's message and no list.
- **Automated:** `RegistrationOverviewPage.test.jsx`, `ManagedRegistrationsPage.test.jsx`

**TC-72-19 · Load failure and retry**
- **Traces to:** AC6 · **Type:** Frontend
- **Expected result:** On a retryable failure (or no connection) the error is shown with a Retry button and no event data; retrying shows the data.
- **Automated:** `RegistrationOverviewPage.test.jsx`, `ManagedRegistrationsPage.test.jsx`

**TC-72-20 · Moving between events never shows the wrong event's figures**
- **Traces to:** AC6 · **Type:** Frontend
- **Expected result:** Moving from one event's overview to another that fails leaves none of the first event's figures. A late reply for the earlier event, success or failure, arriving after the current event's is ignored.
- **Automated:** `RegistrationOverviewPage.test.jsx`

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 03, 15 |
| AC2 | 04, 05, 16 |
| AC3 | 01, 06, 07 |
| AC4 | 06, 08, 09, 10, 17 |
| AC5 | 11, 12, 18 |
| AC6 | 13, 14, 19, 20 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 02, 03, 04 |
| Negative (authorisation) | 07, 08, 09, 10 |
| Negative (privacy) | 05 |
| Negative (failure) | 13, 14 |
| Boundary | 06 |
| Empty state | 11, 12 |
| Frontend | 15, 16, 17, 18, 19, 20 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Should a Coordinator Lead (or an admin) also see registration information for the events they supervise? Assumed only the event's current coordinator. | A1, TC-72-07, TC-72-09 |
| Q2 | Should cancelled or rejected events stay in the list? Assumed every assigned event is listed, as in SCRUM-62. | A2, TC-72-01 |
| Q3 | Do coordinators need to know who registered (for example, for name badges or dietary needs), or only the numbers? Assumed only the numbers; attendee details stay with the organiser (SCRUM-54). | A4, TC-72-04, TC-72-05 |
