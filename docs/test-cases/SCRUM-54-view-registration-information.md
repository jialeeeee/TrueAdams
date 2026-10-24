# SCRUM-54 — Event Organiser Views Registration Information: Test Cases

**User story:** As an Event Organiser, I want to view registration information for the events I manage so that I can track attendance and make decisions about my events.

**Created:** 24 Oct 2026 (story reopened with new acceptance criteria) · **Status of all cases:** Automated cases pass (24 Oct 2026, Supabase + Vitest). · **Automated tests:** `backend/tests/test_organiser_registrations.py`, `frontend/src/pages/OrganisedEventsPage.test.jsx`, `frontend/src/pages/EventRegistrationsPage.test.jsx` · **Endpoints:** `GET /api/events/organised` (new), `GET /api/events/<id>/registrations` (new) · **Related:** SCRUM-45 (registering, places and registration period), SCRUM-68 (withdrawing), SCRUM-62 (the coordinator's managed-events list, same shape), SCRUM-74 (registration numbers on the event page)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The Event Organiser can see a list of the events they manage, each with its registration summary (e.g. total registrations, capacity, remaining places). |
| AC2 | The Event Organiser can open an event to see its registration details (e.g. attendee name, registration date, registration status). |
| AC3 | Only events the Event Organiser manages are shown. Registration information for other events is not visible. |
| AC4 | If the Event Organiser tries to access registration information for an event they don't manage, access is denied and a message is displayed. |
| AC5 | If an event has no registrations, the system shows that there are none instead of an empty or broken view. |
| AC6 | If the registration information cannot be retrieved, an error is displayed and no partial or incorrect data is shown. |

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Whose events:** an organiser manages the events whose organiser (`Event.organiser_id`) they are, and only while their role is `organiser`, read from the database on every request (`is_current_organiser`). Everyone else, including admins and the event's coordinator, gets HTTP 403. *(Q5)*
- **A2 — Which events are listed:** every non-draft event the organiser owns, whatever its status. Drafts cannot take registrations, so they are left out. Events that have not set up registration are still listed, with capacity and remaining places "Not set up". *(Q1)*
- **A3 — Total registrations:** the number of `registered` registrations, the same count SCRUM-45 and SCRUM-74 use for places taken. Withdrawn and cancelled registrations do not count. Remaining places are capacity minus that count, never below 0; with no capacity set, both are `null`. *(Q2)*
- **A4 — Which registrations are listed:** every registration for the event, whatever its status, so the organiser can see who withdrew. Earliest registration first, ties by registration ID. *(Q3)*
- **A5 — Attendee name:** user accounts do not record a name yet, so the attendee's email identifies them. Adding a name needs a schema change and a way to collect it. *(Q4)*
- **A6 — Registration date:** `registered_at` is an audit timestamp (naive UTC), so the page shows it in the viewer's local time, as other audit times are shown.
- **A7 — Order of the list:** soonest proposed date first, undated last, ties by event ID, as SCRUM-62 A4.
- **A8 — Refusal:** an event that does not exist is HTTP 404; an event someone else organises is HTTP 403 with a message saying so, and nothing about the event or its attendees. The check order is 401 → 404 → 403, as AGENTS.md requires.
- **A9 — Load failure:** HTTP 503 with `retryable: true` and no event or registration data, even if part of it had loaded. The page shows the message with a Retry button and no data.

## Endpoints under test

- `GET /api/events/organised` → **200** `{"events": [event, ...], "message": str | null}`.
  - event = `{"id", "title", "start_time", "status", "registration": summary}`; `title` and `start_time` are `null` when not recorded.
  - summary = `{"capacity", "registered_count", "slots_remaining"}`; `capacity` and `slots_remaining` are `null` when no capacity is set.
  - `message` is the empty-state text when the list is empty, otherwise `null`.
  - **401** without a valid session; **403** for anyone who is not an organiser; **503** `{"error", "retryable": true}` if loading fails.
- `GET /api/events/<id>/registrations` → **200** `{"event": event, "registrations": [registration, ...], "message": str | null}`.
  - registration = `{"id", "attendee": {"id", "email"}, "registered_at", "status"}`.
  - `message` is the empty-state text when there are no registrations, otherwise `null`.
  - **401** without a valid session; **404** for an unknown event; **403** for an event the caller does not organise; **503** `{"error", "retryable": true}` if loading fails.

## Seed data (RI-SEED)

Users come from `backend/tests/seed_data.py`, plus three attendees made for the test (`att1`–`att3`). Event times are Singapore time; registration times are UTC.

| Ref | Title | Organiser | Status | Proposed date (start) | Places |
|-----|-------|-----------|--------|-----------------------|--------|
| R1 | Alumni Mixer | dana | approved | 20 Nov 2026 18:30 | 50 |
| R2 | Harbour Lights Festival | dana | approved | 12 Dec 2026 17:00 | 2 |
| R3 | Winter Networking Night | dana | submitted | 1 Nov 2026 09:00 | *not set up* |
| R4 | Spring Gala (draft) | dana | draft | 1 Mar 2027 18:00 | *not set up* |
| R5 | Product Launch | evan | approved | 20 Nov 2026 14:00 | 30 |

| Ref | Event | Attendee | Registered at (UTC) | Status |
|-----|-------|----------|---------------------|--------|
| G1 | R1 | att1 | 1 Oct 2026 03:00 | registered |
| G2 | R1 | farah | 2 Oct 2026 01:00 | registered |
| G3 | R1 | att2 | 3 Oct 2026 05:30 | withdrawn |
| G4 | R2 | att1 | 4 Oct 2026 02:00 | registered |
| G5 | R2 | att3 | 4 Oct 2026 06:00 | registered |
| G6 | R5 | att2 | 5 Oct 2026 08:00 | registered |

R3 has no registrations. evan's only event is R5. A new organiser made for the test has no events.

---

## AC1 — The organiser's events with their registration summary

**TC-54-01 · The organiser sees the events they manage, not drafts**
- **Traces to:** AC1, AC3 · **Type:** Happy path · **Depends on:** Q1
- **Steps:** As dana, load `GET /api/events/organised`.
- **Expected result:** HTTP 200. `events` holds R1, R2 and R3; not the draft R4 and not evan's R5. `message` is `null`.
- **Automated:** `test_organiser_sees_their_non_draft_events_only`

**TC-54-02 · Each event shows its registration summary**
- **Traces to:** AC1 · **Type:** Happy path · **Depends on:** Q2
- **Expected result:** R1 has capacity 50, 2 registered (the withdrawn G3 is not counted) and 48 remaining. R2 has capacity 2, 2 registered and 0 remaining. R3 has capacity `null`, 0 registered and remaining `null`. Each event also has its name, proposed date and status.
- **Automated:** `test_each_event_shows_its_registration_summary`

**TC-54-03 · Soonest proposed date first**
- **Traces to:** AC1 · **Type:** Happy path
- **Expected result:** R3, R1, R2.
- **Automated:** `test_events_are_listed_soonest_first`

## AC2 — An event's registration details

**TC-54-04 · Opening an event lists its registrations**
- **Traces to:** AC2 · **Type:** Happy path · **Depends on:** Q3, Q4
- **Steps:** Take R1's ID from dana's list and load `GET /api/events/<id>/registrations`.
- **Expected result:** HTTP 200. `registrations` holds G1, G2 and G3 in that order (earliest first), each with the attendee's ID and email, `registered_at` as recorded (`"2026-10-01T03:00:00"` for G1) and its status (G3 is `withdrawn`). `message` is `null`.
- **Automated:** `test_opening_an_event_lists_each_registration`

**TC-54-05 · The details repeat the event's summary**
- **Traces to:** AC2 · **Type:** Happy path
- **Expected result:** `event` is R1 with the same summary as in the list (50 places, 2 registered, 48 remaining).
- **Automated:** `test_details_show_the_events_summary`

## AC3 — Only the organiser's own events

**TC-54-06 · Another organiser's events and attendees never appear**
- **Traces to:** AC3 · **Type:** Negative (authorisation)
- **Steps:** Load dana's list and each of her events' details; load evan's list.
- **Expected result:** dana's responses contain neither R5's title nor G6's attendee. evan's list holds only R5.
- **Automated:** `test_other_organisers_events_and_attendees_are_not_visible`

**TC-54-07 · Only organisers, with a valid session, checked on every request**
- **Traces to:** AC3 · **Type:** Negative (authorisation) · **Depends on:** Q5
- **Steps:** Load the list as admin, alice, farah, gus and hana; with no token, an expired token and a deleted user's token; and as dana after her role is changed to attendee (using her earlier token).
- **Expected result:** HTTP 403 for the other roles and for dana after the change; HTTP 401 for the session cases. No event details are returned.
- **Automated:** `test_only_organisers_with_a_valid_session_have_the_list`

## AC4 — Access denied for events the organiser doesn't manage

**TC-54-08 · Another organiser's event is refused with a message**
- **Traces to:** AC4 · **Type:** Negative (authorisation)
- **Steps:** As dana, load R5's registrations.
- **Expected result:** HTTP 403 with a message saying she can only view registration information for events she organises. The response contains neither R5's title nor any attendee's email.
- **Automated:** `test_another_organisers_event_is_refused_with_a_message`

**TC-54-09 · Non-organisers are refused, including the event's coordinator**
- **Traces to:** AC4 · **Type:** Negative (authorisation) · **Depends on:** Q5
- **Steps:** Make alice R1's coordinator. Load R1's registrations as admin, alice, farah, gus and hana.
- **Expected result:** HTTP 403 for each, with a message and no event or attendee details.
- **Automated:** `test_non_organisers_are_refused_an_events_registrations`

**TC-54-10 · Unknown event and invalid session**
- **Traces to:** AC4 · **Type:** Negative
- **Steps:** Load the registrations of an event ID that does not exist, as dana; load R1's registrations without a token.
- **Expected result:** HTTP 404 "Event not found."; HTTP 401.
- **Automated:** `test_unknown_event_is_not_found_and_a_session_is_required`

## AC5 — No registrations

**TC-54-11 · An event with no registrations says so**
- **Traces to:** AC5 · **Type:** Empty state
- **Steps:** As dana, load R3's registrations.
- **Expected result:** HTTP 200. `registrations` is empty, `message` is a non-empty sentence, and `event` still shows R3 with 0 registered.
- **Automated:** `test_event_with_no_registrations_says_there_are_none`

**TC-54-12 · An organiser with no events**
- **Traces to:** AC5 · **Type:** Empty state
- **Steps:** Load the list as an organiser with no events.
- **Expected result:** `events` is empty and `message` is a non-empty sentence.
- **Automated:** `test_organiser_with_no_events_gets_an_empty_state_message`

## AC6 — Loading fails

**TC-54-13 · The list fails as a whole and can be retried**
- **Traces to:** AC6 · **Type:** Negative (failure)
- **Preconditions:** (a) every database query fails; (b) only the registration counts fail, after the events have loaded.
- **Expected result:** HTTP 503 with `retryable: true` and a message saying the information could not be loaded and to try again, with no `events` and no event titles in either case. Loading again with the database working succeeds.
- **Automated:** `test_list_load_failure_returns_no_partial_data_and_retry_works`

**TC-54-14 · The details fail as a whole and can be retried**
- **Traces to:** AC6 · **Type:** Negative (failure)
- **Preconditions:** The event loads, then loading its registrations fails.
- **Expected result:** HTTP 503 with `retryable: true`, a message to try again, and no `event`, `registrations`, title or attendee emails. Loading again succeeds.
- **Automated:** `test_details_load_failure_returns_no_partial_data_and_retry_works`

## Frontend

**TC-54-15 · The list shows each event's registration summary**
- **Traces to:** AC1 · **Type:** Frontend
- **Expected result:** The page "Registrations for my events" lists each event with its name, "Proposed date: …", "Status: …", "Registrations: n", "Capacity: n" and "Remaining places: n". Without a capacity, capacity and remaining places say "Not set up".
- **Automated:** `OrganisedEventsPage.test.jsx`

**TC-54-16 · Each name opens the event's registrations**
- **Traces to:** AC2 · **Type:** Frontend
- **Expected result:** Each name links to `/events/<id>/registrations`.
- **Automated:** `OrganisedEventsPage.test.jsx`

**TC-54-17 · The details show each registration**
- **Traces to:** AC2 · **Type:** Frontend
- **Expected result:** The event's name and summary are shown, then a table with columns Attendee, Registered on and Status: the attendee's email, the registration time in local time and "Registered" or "Withdrawn".
- **Automated:** `EventRegistrationsPage.test.jsx`

**TC-54-18 · Access denied is shown with no data and no Retry**
- **Traces to:** AC4 · **Type:** Frontend
- **Expected result:** On HTTP 403 the server's message is shown, with no event information, no table and no Retry button.
- **Automated:** `EventRegistrationsPage.test.jsx`

**TC-54-19 · Empty states**
- **Traces to:** AC5 · **Type:** Frontend
- **Expected result:** With no registrations, the server's message is shown with the event's summary and no table. With no events, the list page shows the server's message and no list.
- **Automated:** `EventRegistrationsPage.test.jsx`, `OrganisedEventsPage.test.jsx`

**TC-54-20 · Load failure, no stale data, and retry**
- **Traces to:** AC6 · **Type:** Frontend
- **Expected result:** On a retryable failure (or no connection) the error is shown with a Retry button and no event data. Moving from one event's registrations to another that fails to load leaves none of the first event's data on screen. Retrying successfully shows the data.
- **Automated:** `EventRegistrationsPage.test.jsx`, `OrganisedEventsPage.test.jsx`

**TC-54-21 · A late reply for an earlier event is ignored**
- **Traces to:** AC6 · **Type:** Frontend (added after review of PR #51)
- **Steps:** Open event 7's registrations and, before its reply arrives, move to event 9. Event 9's reply arrives first; event 7's arrives afterwards, as a success or as a failure.
- **Expected result:** The page keeps showing event 9's details and registrations. Nothing from event 7 appears and no error is shown.
- **Automated:** `EventRegistrationsPage.test.jsx`

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 03, 15 |
| AC2 | 04, 05, 16, 17 |
| AC3 | 01, 06, 07 |
| AC4 | 08, 09, 10, 18 |
| AC5 | 11, 12, 19 |
| AC6 | 13, 14, 20, 21 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 02, 03, 04, 05 |
| Negative (authorisation) | 06, 07, 08, 09, 10 |
| Negative (failure) | 13, 14 |
| Empty state | 11, 12 |
| Frontend | 15, 16, 17, 18, 19, 20, 21 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Which events should the list show: every submitted event, or only approved events that take registrations? Assumed every non-draft event, with "Not set up" where registration has not been set up. | A2, TC-54-01 |
| Q2 | Should "total registrations" count only current registrations, or also people who withdrew or were cancelled? Assumed current (`registered`) only, matching the places taken. | A3, TC-54-02 |
| Q3 | Should the details list people who withdrew or were cancelled? Assumed yes, with their status. | A4, TC-54-04 |
| Q4 | Accounts record no name. Is the attendee's email acceptable in place of a name, and may organisers see attendees' emails at all? If a name is needed, it must be collected (a schema change). | A5, TC-54-04, TC-54-17 |
| Q5 | Should admins or the event's coordinator also see this information? Assumed only the event's organiser. | A1, TC-54-07, TC-54-09 |
