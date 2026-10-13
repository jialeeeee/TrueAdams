# SCRUM-74 — View Event Details: Test Cases

**User story:** As a signed-in user, I want to open an event's details page, so that I can decide whether to register and see my own registration.

**Created:** 13 Oct 2026 · **Status of all cases:** Written test-first (TDD, red). Nothing is implemented yet, so every automated test fails until the feature is built. · **Automated tests:** `backend/tests/test_event_details.py`, `frontend/src/pages/EventDetailsPage.test.jsx`, `frontend/src/pages/EventsPage.test.jsx` · **Endpoints:** `GET /api/events/` (replaces the stub) and `GET /api/events/<id>` · **Related:** SCRUM-45 (registering; owns the registration period, capacity and `Registration`), SCRUM-68 (withdrawing), SCRUM-61 (the page carries "Request reassignment")

**Source:** the team's "Sprint 2 test cases" sheet (IS212-US74-TC1 to TC17). Case `TC-74-nn` automates sheet case `IS212-US74-TCn`. Sheet users map to the seed data below: attendee_eve is farah (not registered), attendee_dan is ivy (registered) and coord_alice is alice; the sheet's events E-301 to E-309 are E1 to E10 here.

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | Any signed-in user can open an event's detail page from the event list. |
| AC2 | The page shows name, description, date, start and end time, venue name and location, registration period, capacity and slots remaining. |
| AC3 | Attendees can only view events they are authorised to see (published); draft, rejected and pending events return "not found". |
| AC4 | Event creators and approvers can also view their own unpublished events, with the status shown. |
| AC5 | The page shows whether registration is Open, Closed or Full. |
| AC6 | If the user is registered, the page shows their registration status. |
| AC7 | An invalid or non-existent event ID shows a friendly "Event not found" page, not an error trace. |
| AC8 | Empty optional fields (e.g. the description) show "Not provided", never blank or "null". |
| AC9 | Slots remaining updates after registering and withdrawing (consistent with SCRUM-45 and SCRUM-68). |
| AC10 | A "Register" button shows only when registration is open, there is room and the user is not already registered; otherwise the reason is shown. |
| AC11 | Dates and times use one format (dd/mm/yyyy) and Singapore time (SGT). |
| AC12 | Signed-out users are sent to the sign-in page. |

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Published:** an event is published when its status is `confirmed`, the status SCRUM-45 uses for events that take registrations. `draft`, `submitted` (pending), `under_review` and `rejected` are not published. `approved` and `cancelled` are deliberately not covered by any test: the sheet calls an approved event visible, but the repo treats `confirmed` as the public status. *(Q1)*
- **A2 — Who sees an unpublished event:** its organiser, its assigned coordinator and admins. Everyone else, including other organisers, other coordinators and staff, gets the same HTTP 404 and body (`{"error": "Event not found."}`) that an unknown ID gets, so the two cannot be told apart and nothing about the event leaks. *(Q2)*
- **A3 — The list:** `GET /api/events/` is the public catalogue: only published events, soonest first, for every role, each with `registration_state`. Creators find their drafts through My drafts and My event requests, not here. `message` is set only when the list is empty. *(Q2)*
- **A4 — Registration state:** `closed` if registration is not set up (not required, or no capacity, or no period) or now is outside the period (open from the opening time up to, not including, the closing time, as SCRUM-45 does); otherwise `full` when no places remain; otherwise `open`. Closed wins over full. The state is computed here from the same fields, with "now" from `app.events.routes.singapore_now()`.
- **A5 — Places:** `registered_count` counts only `registered` registrations (not waiting-list, withdrawn or cancelled ones). `slots_remaining` is capacity minus that, never below zero, and null with capacity when capacity is not recorded.
- **A6 — My registration:** the caller's own `registered` or `waitlisted` registration as `{"id", "status"}`, otherwise null. Withdrawn and cancelled ones are not shown. Other attendees' details are never returned.
- **A7 — Register button:** `can_register` is true only for an attendee when the state is `open` and they have no active registration. Otherwise `register_blocked_reason` is `already_registered`, `full`, `closed` or `not_attendee`, checked in that order (so an attendee already registered for a full event sees their status). A full event with a waiting list does not offer Register on this page; joining the list is a later improvement. *(Q3)*
- **A8 — Not provided:** the API returns null for a missing or blank description and for a missing venue or venue location (the repo's "NULL means not recorded" rule); the page turns null into "Not provided".
- **A9 — Times:** returned as naive Singapore time in ISO 8601 (`2026-11-20T10:00:00`), unchanged, in both the list and the detail. The page shows `dd/mm/yyyy HH:MM SGT` by reformatting the text, never through the browser's time zone, so 23:30 stays on the same day. The sheet asks for this format; `AGENTS.md` suggests showing the raw time, so this is a small shared helper. *(Q4)*
- **A10 — Unknown and malformed IDs:** HTTP 404 `{"error": "Event not found."}` for an unknown ID. A malformed ID (`abc'--`, `-1`) never reaches the database and gets a 404. An ID too large for the database column (over 2,147,483,647) also gets 404, not a 503. No response contains a stack trace or database text.
- **A11 — Order of checks:** not signed in (401) → unknown, malformed or hidden event (404). There is no 403 here: a refusal must not reveal that an event exists.
- **A12 — Page and sign-in:** `EventDetailsPage` at `/events/:eventId`, linked from `EventsPage`. "Register" is a link to the existing `/events/:eventId/register` page. Pages treat an HTTP 401 as signed out and go to `/login`. The event's `status` is shown only when it is not `confirmed`. The detail also carries `can_request_reassignment` for SCRUM-61. *(Q5)*

## Endpoints under test

- `GET /api/events/`:
  - **200** `{"events": [{"id", "title", "start_time", "end_time", "registration_state"}], "message": str or null}`.
  - **401** (no valid session).
- `GET /api/events/<id>`:
  - **200** `{"event": {"id", "title", "description", "status", "start_time", "end_time", "venue": {"name", "location"} or null, "registration": {"state", "opens_at", "closes_at", "capacity", "registered_count", "slots_remaining"}, "my_registration": {"id", "status"} or null, "can_register", "register_blocked_reason", "can_request_reassignment"}}`.
  - **401**; **404** `{"error": "Event not found."}`.

## What the implementation needs

- In `app/events/routes.py`: replace the `list_events` stub, add `GET /<int:event_id>` (the route already exists for `PATCH`), a `PUBLISHED_STATUSES = {"confirmed"}` constant with a comment, and `singapore_now` imported from `app.registrations.routes`. No schema change.
- `frontend/src/pages/EventDetailsPage.jsx` (route `/events/:eventId`), a new `EventsPage.jsx` that lists links to it, and a small helper in `frontend/src/utils/` that reformats a Singapore-time string to `dd/mm/yyyy HH:MM SGT`.
- `test_routes.py`: `GET /api/events/` leaves `COLLECTION_ENDPOINTS` (it now needs a login and returns an object), and `GET /api/events/1` joins `ALL_ROUTES`.

## Seed data (DT-SEED)

"Now" is fixed at **5 Nov 2026 12:00** Singapore time. Users come from `backend/tests/seed_data.py`, plus extra attendees `ivy`, `jon` and `kim`. Every event is organised by dana and coordinated by alice.

Unless the table says otherwise, an event is `confirmed`, has the description "Open house for O-Level chemistry", runs 20 Nov 2026 10:00 – 12:00, has no venue, takes registrations from 1 Nov 2026 00:00 to 15 Nov 2026 00:00, has 5 places and no waiting list.

| Ref | Title | Differs from the defaults | Registrations already made |
|-----|-------|---------------------------|----------------------------|
| E1 | Chem Open House | venue "Seminar Room 2", location "SMU Library, 70 Stamford Rd" | ivy, jon registered; kim withdrawn |
| E2 | Closed Fair | period 1 Sep – 30 Sep 2026 (over) | jon registered; kim waitlisted |
| E3 | Draft Workshop | status `draft` | none |
| E4 | Pending Talk | status `submitted` | none |
| E5 | Review Panel | status `under_review` | none |
| E6 | Rejected Rally | status `rejected` | none |
| E7 | Last Place Gala | 2 places | jon registered (1 left) |
| E8 | Full House | 2 places | jon, kim registered (full) |
| E9 | No Details Yet | no description | none |
| E10 | Blank Details | description is only spaces | none |

The signed-in user is farah (an attendee who is not registered anywhere) unless a case says otherwise. The sheet uses capacity 30; the seed uses smaller numbers so the cases stay fast.

---

## AC1 — The way in

**TC-74-01 · An attendee opens an event from the list** *(sheet TC1)*
- **Traces to:** AC1 · **Type:** Happy path
- **Steps:** As farah, `GET` the list and open E1 by the ID in its entry. Repeat the list and detail calls as dana, alice, gus, hana and admin. Move E7 before E1 and read the list again.
- **Expected result:** The list holds E1 with only `id`, `title`, `start_time`, `end_time` and `registration_state`, and its detail opens (HTTP 200). Every role can use both. The list is soonest first, and shows the registration state of each event (`open`, `closed`, `full`). The page lists each event as a link to `/events/<id>` with its start time and registration state ("Starts: 20/11/2026 10:00 SGT", "Registration: Open"), shows the server's message when the list is empty, and offers Retry when the list could not be loaded.
- **Automated:** `ListTests.test_attendee_opens_an_event_from_the_list`, `test_every_role_can_view_a_published_event`, `test_list_is_soonest_first_with_registration_state`; frontend (`EventsPage`): "lists each published event as a link to its details", "shows when each event starts and whether registration is open, in Singapore time", "shows the server's message when there are no events", "shows why the list could not be loaded and lets the user try again", "shows a fallback message when the server cannot be reached".

## AC2 — What the page shows

**TC-74-02 · Every required field is shown** *(sheet TC2)*
- **Traces to:** AC2 · **Type:** Happy path
- **Steps:** As farah, open E1.
- **Expected result:** Exactly the contract in "Endpoints under test": title, description, `confirmed`, `2026-11-20T10:00:00` to `2026-11-20T12:00:00`, venue name and location, the period `2026-11-01T00:00:00` to `2026-11-15T00:00:00`, capacity 5, 2 registered, 3 slots remaining, state `open`, no registration of her own, `can_register: true` and `can_request_reassignment: false`. The page shows each as a labelled line ("Starts: 20/11/2026 10:00 SGT", "Capacity: 5", "Slots remaining: 3", "Registration: Open").
- **Automated:** `FieldTests.test_all_required_fields_are_shown`; frontend: "shows every required field".

## AC3, AC4 — Who may see which event

**TC-74-03 · An attendee cannot see a draft** *(sheet TC3)*
- **Traces to:** AC3 · **Type:** Negative (authorisation) · **Depends on:** Q1
- **Steps:** As farah, `GET` the list, then open E3 directly. Compare the answer with the one for an ID no event has.
- **Expected result:** E3 is not in the list. The detail gives HTTP 404 `{"error": "Event not found."}` with no trace of the title, and its body and status are identical to the unknown ID's.
- **Automated:** `VisibilityTests.test_attendee_cannot_see_a_draft`.

**TC-74-04 · Pending, under-review and rejected events are hidden too** *(sheet TC4)*
- **Traces to:** AC3 · **Type:** Negative (authorisation) · **Depends on:** Q1
- **Steps:** As farah, open E4 (submitted), E5 (under review) and E6 (rejected). As farah, dana, alice and admin, read the list.
- **Expected result:** HTTP 404 for all three, and none is in the list for any of the four users.
- **Automated:** `VisibilityTests.test_attendee_cannot_see_pending_or_rejected_events`, `test_list_shows_published_events_only`.

**TC-74-05 · The creator and approvers see their own unpublished events** *(sheet TC5)*
- **Traces to:** AC4 · **Type:** Happy path (counterpart of TC-74-03) · **Depends on:** Q2
- **Steps:** As dana (organiser), alice (the event's coordinator) and admin, open E3 to E6. Then, as evan (another organiser), ben (a coordinator who is not assigned), gus, hana and farah, open E3 and E4.
- **Expected result:** The first three see each event with its real status (`draft`, `submitted`, `under_review`, `rejected`) and title. The rest get the same 404 an unknown ID gets. The page shows "Status: Draft" for an unpublished event and no status line for a published one.
- **Automated:** `VisibilityTests.test_creator_and_approvers_can_see_unpublished_events`, `test_other_users_cannot_see_unpublished_events`; frontend: "shows the event's status to someone viewing an unpublished event, and not otherwise", "does not show a status line for a published event".

## AC5 — Open, Closed or Full

**TC-74-06 · One place left is still Open** *(sheet TC6)*
- **Traces to:** AC5 · **Type:** Boundary
- **Steps:** As farah, open E7 (2 places, 1 registered).
- **Expected result:** State `open`, 1 registered, 1 slot remaining.
- **Automated:** `RegistrationStateTests.test_one_place_left_is_open`.

**TC-74-07 · No places left is Full** *(sheet TC7)*
- **Traces to:** AC5 · **Type:** Boundary
- **Steps:** As farah, open E8 (2 places, 2 registered). Open E2, where jon is registered and kim is waitlisted, and E1, where kim is withdrawn.
- **Expected result:** E8: state `full`, 0 slots remaining, `can_register: false`. Only registered attendees count: E2 has 1 registered (the waiting-list place does not count) and E1 has 2 (the withdrawn one does not).
- **Automated:** `RegistrationStateTests.test_no_places_left_is_full`, `test_only_registered_attendees_take_places`.

**TC-74-08 · Closed outside the period, or when registration is not set up** *(sheet TC8)*
- **Traces to:** AC5 · **Type:** Negative, boundary
- **Steps:** Open E2 (period over, 4 places left). For E1, set now to 31 Oct 23:59, 1 Nov 00:00, 14 Nov 23:59 and 15 Nov 00:00. For E8 (full) set now to the closing time. For E1, remove the capacity, then the "registration needed" flag, then the closing time.
- **Expected result:** E2: state `closed` with 4 slots remaining. E1: `closed`, `open`, `open`, `closed`, in that order. E8 after closing: `closed`, not `full`. E1 with no capacity: `closed`, capacity and slots remaining null; the other two removals also give `closed`.
- **Automated:** `RegistrationStateTests.test_outside_the_period_is_closed_even_with_places_left`, `test_period_boundaries`, `test_closed_beats_full`, `test_registration_that_is_not_set_up_is_closed`; frontend: "shows whether registration is open", "shows whether registration is closed", "shows whether registration is full".

## AC6 — My registration

**TC-74-09 · A registered attendee sees their status** *(sheet TC9)*
- **Traces to:** AC6 · **Type:** Happy path
- **Steps:** As ivy, open E1. As kim, open E2.
- **Expected result:** Ivy: `my_registration` is `{"id": <her registration>, "status": "registered"}`. Kim, on the waiting list: status `waitlisted`. The page shows "Your registration: Registered" or "Your registration: Waitlisted".
- **Automated:** `MyRegistrationTests.test_registered_attendee_sees_their_status`, `test_waitlisted_attendee_sees_waitlisted`; frontend: "shows the attendee's own registration status", "shows a waiting-list place as Waitlisted".

**TC-74-10 · An unregistered attendee sees no registration status** *(sheet TC10)*
- **Traces to:** AC6 · **Type:** Negative
- **Steps:** As farah, open E1. As kim, whose registration is withdrawn, open E1.
- **Expected result:** `my_registration` is null for both, and farah's response contains neither ivy's nor jon's email. The page shows no "Your registration" line.
- **Automated:** `MyRegistrationTests.test_unregistered_attendee_sees_no_registration`, `test_withdrawn_registration_is_not_shown`; frontend: "shows no registration status to someone who is not registered".

## AC7 — Not found

**TC-74-11 · An unknown or malformed ID shows a friendly page** *(sheet TC11)*
- **Traces to:** AC7 · **Type:** Negative
- **Steps:** As farah, open an ID no event has, then `abc'--`, `not-an-id`, `-1`, `99999999999999999999` and `2147483648`.
- **Expected result:** HTTP 404 each time, and no response contains "traceback", "sqlalchemy", "psycopg", "select " or "syntax error". The unknown ID's body is `{"error": "Event not found."}`. The page shows "Event not found." and a "Back to events" link, none of the event's details, and the same message even when the server's body is not JSON; other failures offer Retry or a fallback message.
- **Automated:** `NotFoundTests.test_unknown_event_is_not_found`, `test_malformed_ids_do_not_leak_errors`; frontend: "shows a friendly page for an event that is not found, with no details", "shows the same page when the server sends no message", "shows why the event could not be loaded and lets the user try again", "shows a fallback message when the server cannot be reached".

## AC8 — Not provided

**TC-74-12 · Empty optional fields** *(sheet TC12)*
- **Traces to:** AC8 · **Type:** Boundary
- **Steps:** As farah, open E9 (no description, no venue) and E10 (a description of only spaces). Give a venue with no recorded location to E9 and open it.
- **Expected result:** `description` and `venue` are null for both. With a venue and no location, `venue` is `{"name": "Pop-up Tent", "location": null}`. The page shows "Description: Not provided", "Venue: Not provided", "Location: Not provided", "Capacity: Not provided" and "Slots remaining: Not provided" where the data is null, and never "null" or "undefined".
- **Automated:** `FieldTests.test_empty_optional_fields_are_null`, `test_venue_without_a_location`; frontend: "shows 'Not provided' for empty optional fields, never blank or null", "shows 'Not provided' for a venue without a recorded location".

## AC9 — Slots follow registering and withdrawing

**TC-74-13 · Slots change when the attendee registers and withdraws** *(sheet TC13)*
- **Traces to:** AC9 · **Type:** Integration (SCRUM-45, SCRUM-68)
- **Steps:** As farah, open E1 (3 slots). Register for E1 and open it. Withdraw and open it again.
- **Expected result:** 3, then 2 with `my_registration.status` `registered`, then 3 with `my_registration` null. The list shows E1 `open` throughout.
- **Automated:** `SlotsTests.test_slots_remaining_follows_registering_and_withdrawing`.

## AC10 — The Register button

**TC-74-14 · Register is offered when registration is possible** *(sheet TC14)*
- **Traces to:** AC10 · **Type:** Happy path
- **Steps:** As farah, open E1.
- **Expected result:** `can_register: true` and no blocking reason. The page shows a "Register" link to `/events/<id>/register`.
- **Automated:** `RegisterButtonTests.test_register_is_offered_when_registration_is_possible`; frontend: "offers Register only when registration is possible".

**TC-74-15 · Register is replaced by the reason** *(sheet TC15)*
- **Traces to:** AC10 · **Type:** Negative · **Depends on:** Q3
- **Steps:** Open E1 as ivy (already registered), E8 as farah (full), E2 as farah (closed) and E8 as jon (full, but he is registered). Open E1 as dana, alice, admin and gus.
- **Expected result:** `can_register: false` with reasons `already_registered`, `full`, `closed` and `already_registered` (registered beats full), and `not_attendee` for the staff roles. The page shows no Register link or button, and shows "Your registration: Registered", "Registration: Full" or "Registration: Closed".
- **Automated:** `RegisterButtonTests.test_register_is_replaced_by_the_reason`, `test_only_attendees_are_offered_register`; frontend: "replaces Register with the reason (already_registered)", "(full)", "(closed)".

## AC11 — Date and time format

**TC-74-16 · Times are Singapore time as recorded** *(sheet TC16)*
- **Traces to:** AC11 · **Type:** Boundary · **Depends on:** Q4
- **Steps:** Move E1 to 20 Nov 23:30 – 21 Nov 01:00. Open it and the list.
- **Expected result:** The detail and the list both return `2026-11-20T23:30:00` and `2026-11-21T01:00:00`: ISO 8601 with no offset and no conversion. The page shows "Starts: 20/11/2026 23:30 SGT" and "Ends: 21/11/2026 01:00 SGT", the same day as recorded, whatever the browser's time zone.
- **Automated:** `FieldTests.test_times_are_singapore_time_as_recorded`; frontend: "shows times as recorded in Singapore time, whatever the browser's time zone".

## AC12 — Signed out

**TC-74-17 · Signed-out users are sent to sign in** *(sheet TC17)*
- **Traces to:** AC12 · **Type:** Negative (authentication)
- **Steps:** `GET` the list and E1 with no token, an expired token and the token of a deleted user.
- **Expected result:** HTTP 401 every time, and nothing about E1 in the body. The pages go to `/login` and show no events or details.
- **Automated:** `SignedOutTests.test_signed_out_users_get_401`; frontend: "sends a signed-out user to the sign-in page and shows no events", "sends a signed-out user to the sign-in page and shows no details".

## SCRUM-61 entry point on this page

The event page shows "Request reassignment" (a link to `/events/<id>/reassign`) only when the API says `can_request_reassignment` is true. The API side is TC-61-01 to TC-61-03.
- **Automated:** frontend: "offers Request reassignment to the event's main coordinator", "does not offer Request reassignment to anyone else".

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01 |
| AC2 | 02 |
| AC3 | 03, 04 |
| AC4 | 05 |
| AC5 | 06, 07, 08 |
| AC6 | 09, 10 |
| AC7 | 11 |
| AC8 | 12 |
| AC9 | 13 |
| AC10 | 14, 15 |
| AC11 | 16 |
| AC12 | 17 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 02, 05, 09, 14 |
| Negative | 03, 04, 08, 10, 11, 15, 17 |
| Boundary | 06, 07, 08, 12, 16 |
| Integration | 13 |
| Cross-cutting (authorisation) | 03, 04, 05 |
| Cross-cutting (authentication) | 17 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Which statuses are public? The sheet says approved/published; the registration story treats only `confirmed` as open. Should `approved` events be visible to attendees, and should a `cancelled` event stay visible to people who registered for it? Assumed: only `confirmed`. | A1, TC-74-03, 04 |
| Q2 | Who counts as an "approver" who may see an unpublished event, and should creators see their drafts in the main event list? Assumed: the organiser, the assigned coordinator and admins; the list is public only. | A2, A3, TC-74-05 |
| Q3 | When an event is full but has a waiting list, should the page offer "Join the waiting list"? Assumed: not in this story. | A7, TC-74-15 |
| Q4 | Is dd/mm/yyyy plus "SGT" the format everywhere, or only on this page? The rest of the app shows `yyyy-mm-dd hh:mm`. | A9, TC-74-16 |
| Q5 | Where should signed-out users land after sign-in: the page they asked for, or the home page? Assumed: the sign-in page only. | A12, TC-74-17 |
