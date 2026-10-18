# SCRUM-45 — Register for an Event: Test Cases

**User story:** As an Attendee, I want to register for an event so that I can secure my place.

**Created:** 9 Oct 2026 · **Reopened:** 18 Oct 2026 (an event must be **Approved**, and the waiting list is **removed**; see *What changed on reopening*) · **Status of all cases:** Automated cases pass (18 Oct 2026, local PostgreSQL 17 with db/remove_waitlist.sql applied + Vitest); TC-45-22 is checked manually. · **Automated tests:** `backend/tests/test_event_registration.py`, `frontend/src/pages/EventRegistrationPage.test.jsx` · **Endpoint:** `POST /api/registrations/` · **Related:** SCRUM-29 (`registration_required`), SCRUM-52/53 (which event fields can be edited directly), SCRUM-68 (withdrawal, which promoted from the waiting list), SCRUM-74 (event details, which publishes the same status)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | I can register only if the event status is Approved, registration is enabled and within its registration period, and places are available. |
| AC2 | On success exactly one active registration is created and linked to me, and a confirmation is shown. |
| AC3 | If I already have an active registration, no second one is created and my existing status is shown. |
| AC4 | If the event is full, registration is blocked with the message "This event is full". |
| AC5 | If registration is closed or disabled, it is blocked with a message that says which. |
| AC6 | If saving fails, no registration is created and an error is shown. |

## What changed on reopening (18 Oct 2026)

Following the Week 7 *Guide to Managing Changes*, test-case IDs are kept: changed cases say what changed, and retired ones stay listed.

- **Approved, not "Confirmed" (AC1):** no story ever set an event's status to `confirmed`, so registration was never possible. Registration now needs `approved`, the status SCRUM-32 sets. SCRUM-74 publishes the same status, so attendees can find these events.
- **No waiting list (AC4):** the waiting list is removed. A full event is blocked with "This event is full.", and nobody is waitlisted. The `events.waitlist_enabled` column is dropped and the one-active-registration index counts `registered` rows only (`db/remove_waitlist.sql`). Any existing `waitlisted` registrations become `cancelled`: they never held a place. SCRUM-68's promotion from the waiting list on withdrawal is removed too.
- **Changed cases:** TC-45-01, 02, 06, 16, 17, 18, 19, 20, 23. **Retired:** TC-45-13 (already on the waiting list).

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Who registers:** only users whose role is `attendee`, checked against the database on every request. Organisers, coordinators, staff and admins get HTTP 403. An attendee registers only themselves. *(Q1)*
- **A2 — Approved:** only events whose status is `approved` take registrations. Every other status (`draft`, `submitted`, `under_review`, `confirmed`, `rejected`, `cancelled`) is blocked. The refusal does not reveal the event's title or status, because attendees should not learn about requests that are not public.
- **A3 — Registration enabled:** `Event.registration_required` (SCRUM-29's "Attendee registration needed") is `true`. `false` or not recorded means registration is disabled. *(Q3)*
- **A4 — Registration period:** `registration_opens_at` and `registration_closes_at`, in Singapore time without a time zone, like the event's own times. Registration is open from the opening time up to, but not including, the closing time, the same half-open rule as venue scheduling. If either is not recorded, registration is closed. "Now" is the current Singapore time. *(Q4)*
- **A5 — Places:** `registration_capacity` gives the number of places. Only `registered` registrations take a place; `withdrawn` (SCRUM-68) and `cancelled` ones do not. If the capacity is not recorded, registration is treated as disabled. Neither `expected_attendance` (the organiser's estimate) nor the venue's capacity is used for this. *(Q5)*
- **A6 — Full:** when every place is taken, registration is blocked with exactly "This event is full." (AC4). There is no waiting list.
- **A7 — Active registration:** `Registration.status` is `registered`, `withdrawn` (SCRUM-68) or `cancelled`; only `registered` is active. A partial unique index on `(event_id, attendee_id)` for `registered` rows lets the database guarantee one active registration per attendee per event. A withdrawn or cancelled registration does not count, so that attendee can register again with a new row. *(Q7)*
- **A8 — Already registered:** if the attendee already has an active registration, the response is HTTP 200 with that registration unchanged, `already_registered: true`, and a message giving the existing status. This happens **before** the eligibility checks, so an attendee who registered while places were available still sees their status after the event fills or registration closes.
- **A9 — Blocked:** HTTP 409 with a plain message and a machine-readable `reason`: `not_approved`, `disabled` ("Registration has not been enabled for this event."), `not_open_yet` (the message says when registration opens), `closed` ("Registration for this event is closed."), or `full` ("This event is full."). Each reason has its own message, and closed and disabled say which (AC5). Nothing is saved.
- **A10 — Order of checks:** not logged in (401) → not an attendee (403) → invalid body (400) → unknown event (404) → existing active registration (200) → not approved → disabled → before the period → after the period → full (409). The role check comes before the event lookup, so other users cannot probe which event IDs exist. A full event that is also closed, disabled or not approved says which, not "full".
- **A11 — Saving fails:** HTTP 503 with `retryable: true`, saying the registration was not saved and to try again. No row is created, and a retry works once the database is back.
- **A12 — No email:** the confirmation is the response message. No notification or email is sent in this story. *(Q8)*

## Endpoint under test

- `POST /api/registrations/` with body `{"event_id": int}`:
  - **201** `{"message": str, "registration": registration}`: registered.
  - **200** `{"message": str, "registration": registration, "already_registered": true}`: existing active registration.
  - **409** `{"error": str, "reason": str}`: blocked (A9).
  - **400**, **401**, **403**, **404** `{"error": str}`.
  - **503** `{"error": str, "retryable": true}`.
- A registration is `{"id", "event_id", "status", "registered_at"}`. `status` is `registered`, and `registered_at` is naive UTC.

## What the implementation needs

- `Event`: `registration_opens_at` and `registration_closes_at` (DateTime, Singapore time) and `registration_capacity` (Integer), all nullable with no defaults, because NULL means not recorded. `waitlist_enabled` is removed.
- `Registration.status` (String(20), not null, default `registered`), plus a partial unique index on `(event_id, attendee_id) where status = 'registered'`.
- `db/event_registration.sql` (already run), then `db/remove_waitlist.sql`: cancels any `waitlisted` registrations, rebuilds the index for `registered` only, and drops `events.waitlist_enabled`. It must be run on Supabase before merging.
- `app.registrations.routes.singapore_now()` returns the current Singapore time without a time zone. The tests patch it to fix "now".
- The event row is locked (`SELECT … FOR UPDATE`) while places are counted, so two attendees cannot both take the last place (TC-45-22). An `IntegrityError` from the unique index (the same attendee registering twice at once) returns the existing registration instead of failing.
- The status that takes registrations is the one SCRUM-74 publishes, so both read one shared rule.

## Seed data (RG-SEED)

"Now" is fixed at **1 Nov 2026 12:00** Singapore time. Users come from `backend/tests/seed_data.py`, plus two extra attendees, `ivy` and `jon`. Every event is organised by dana, coordinated by alice, and runs 12 Dec 2026 17:00 – 22:00.

Unless the table says otherwise, an event has status `approved`, registration enabled, opens 1 Oct 2026 09:00 and closes 1 Dec 2026 00:00.

| Ref | Title | Capacity | Differs from the defaults | Registrations already made |
|-----|-------|----------|---------------------------|----------------------------|
| E1 | Harbour Lights Festival | 3 | — | none |
| E2 | Winter Networking Night | 2 | — | ivy, jon registered (full) |
| E3 | Product Launch | 1 | — | ivy registered (full) |
| E4 | Rooftop Cinema | 50 | registration disabled | none |
| E5 | Spring Garden Party | 50 | opens 15 Nov 2026 09:00 | none |
| E6 | Alumni Mixer | 50 | closed 1 Nov 2026 00:00 | none |
| E7 | Tech Summit | not recorded | — | none |

The registering attendee is `farah` unless a case says otherwise.

---

## AC1 — Who can register, and for which events

**TC-45-01 · Register for an approved, open event with places** *(changed: approved, not confirmed)*
- **Traces to:** AC1, AC2 · **Type:** Happy path
- **Steps:** As farah, register for E1.
- **Expected result:** HTTP 201 with status `registered` and a confirmation message naming "Harbour Lights Festival".
- **Automated:** `test_register_for_an_approved_open_event_with_places`

**TC-45-02 · Only approved events accept registrations** *(changed)*
- **Traces to:** AC1 · **Type:** Negative (business rule)
- **Steps:** Set E1's status to each of `draft`, `submitted`, `under_review`, `confirmed`, `rejected` and `cancelled` in turn, and register.
- **Expected result:** HTTP 409 with reason `not_approved` each time. The message does not contain the event's title or status. No registration is created.
- **Automated:** `test_only_approved_events_accept_registrations`

**TC-45-03 · Registration disabled**
- **Traces to:** AC1, AC5 · **Type:** Negative · **Depends on:** Q3
- **Steps:** Register for E4. Then set E4's `registration_required` to not recorded and register again.
- **Expected result:** HTTP 409 with reason `disabled` both times. Nothing is saved.
- **Automated:** `test_registration_disabled`

**TC-45-04 · Registration period boundaries**
- **Traces to:** AC1, AC5 · **Type:** Boundary · **Depends on:** Q4
- **Test data (E1, opens 1 Oct 2026 09:00, closes 1 Dec 2026 00:00):** now = 1 Oct 08:59 → `not_open_yet`; now = 1 Oct 09:00 → registered; now = 30 Nov 23:59 → registered; now = 1 Dec 00:00 → `closed`. A different attendee registers each time.
- **Expected result:** As listed. The `not_open_yet` message gives the opening date.
- **Automated:** `test_registration_period_boundaries`

**TC-45-05 · Not yet open, or already closed**
- **Traces to:** AC1, AC5 · **Type:** Negative · **Depends on:** Q4
- **Steps:** Register for E5, then E6. Then remove E1's opening time and register; then remove its closing time instead and register.
- **Expected result:** E5 gives `not_open_yet`; E6 and both incomplete periods give `closed`. Nothing is saved.
- **Automated:** `test_not_yet_open_or_already_closed`

**TC-45-06 · The last place, and what takes a place** *(changed: withdrawn instead of waitlisted)*
- **Traces to:** AC1, AC4 · **Type:** Boundary · **Depends on:** Q5
- **Preconditions:** E1 (capacity 3) has two `registered`, one `withdrawn` and one `cancelled` registration from other attendees.
- **Steps:** farah registers for E1, then another attendee does.
- **Expected result:** farah is `registered` (withdrawn and cancelled registrations do not take places). The next attendee gets HTTP 409 `full`.
- **Automated:** `test_the_last_place_and_what_takes_a_place`

**TC-45-07 · Capacity not recorded**
- **Traces to:** AC1, AC5 · **Type:** Negative · **Depends on:** Q5
- **Steps:** Register for E7.
- **Expected result:** HTTP 409 with reason `disabled`. Nothing is saved.
- **Automated:** `test_capacity_not_recorded`

**TC-45-08 · Only attendees can register**
- **Traces to:** AC1 · **Type:** Negative (authorisation) · **Depends on:** Q1
- **Steps:** Register for E1 as admin, alice, dana, gus and hana. Then, as dana, send an invalid body and an unknown event ID.
- **Expected result:** HTTP 403 every time (the role is checked before the body and the event). Nothing is saved.
- **Automated:** `test_only_attendees_can_register`

**TC-45-09 · Access follows role changes**
- **Traces to:** AC1 · **Type:** Boundary (authorisation)
- **Steps:** Get a token for farah, change her role to organiser, then register for E1 with that token.
- **Expected result:** HTTP 403. Nothing is saved.
- **Automated:** `test_access_follows_role_changes`

**TC-45-10 · A valid session, a valid body and an existing event are required**
- **Traces to:** AC1 · **Type:** Negative
- **Test data:** No token, an expired token and a deleted user's token (401); `event_id` missing, `"1"`, `true`, `1.5` and a body that is not JSON (400); an ID no event has (404).
- **Expected result:** As listed. Nothing is saved.
- **Automated:** `test_session_body_and_event_are_required`

## AC2 — Exactly one registration, linked to me

**TC-45-11 · The registration is saved and linked to the attendee**
- **Traces to:** AC2 · **Type:** Happy path
- **Steps:** As farah, register for E1.
- **Expected result:** Exactly one new registration exists across the seeded events: E1, farah, status `registered`, with `registered_at` between just before and just after the request. The response's `registration` matches the saved row. Other attendees' registrations are unchanged.
- **Automated:** `test_registration_is_saved_and_linked_to_the_attendee`

## AC3 — Already registered

**TC-45-12 · Registering twice shows the existing registration**
- **Traces to:** AC3 · **Type:** Negative (duplicate)
- **Steps:** As farah, register for E1 twice.
- **Expected result:** The second call gives HTTP 200, `already_registered: true`, the same registration (same ID and time), and a message saying she is already registered with status "Registered". Only one registration exists.
- **Automated:** `test_registering_twice_shows_the_existing_registration`

**TC-45-13 · Already on the waiting list** — *Retired on 18 Oct 2026: there is no waiting list.*

**TC-45-14 · The existing status is shown even after registration closes or fills up**
- **Traces to:** AC3 · **Type:** Boundary · **Depends on:** A8
- **Steps:** ivy (registered for E3, now full) registers for E3 again. farah registers for E1, then E1 is cancelled, its registration is disabled, and the clock moves past its closing time; she registers again.
- **Expected result:** HTTP 200 with the existing registration each time, never 409.
- **Automated:** `test_existing_status_is_shown_after_registration_closes_or_fills`

**TC-45-15 · A cancelled registration does not count**
- **Traces to:** AC3 · **Type:** Boundary · **Depends on:** Q7
- **Preconditions:** farah has a `cancelled` registration for E1.
- **Expected result:** Registering gives HTTP 201 with a new `registered` row. The cancelled row is unchanged.
- **Automated:** `test_a_cancelled_registration_does_not_count`

**TC-45-16 · The database allows only one active registration** *(changed: registered only)*
- **Traces to:** AC2, AC3 · **Type:** Negative (data integrity)
- **Steps:** Insert a second `registered` registration for the same attendee and event directly.
- **Expected result:** The insert fails with an integrity error. `cancelled` and `withdrawn` rows next to a `registered` one are allowed.
- **Automated:** `test_database_allows_only_one_active_registration`

## AC4 — A full event

**TC-45-17 · Full: blocked with "This event is full."** *(changed: was "added to the waiting list")*
- **Traces to:** AC4 · **Type:** Negative (business rule)
- **Steps:** As farah, register for E2 (two places, both taken).
- **Expected result:** HTTP 409 with reason `full` and exactly the message "This event is full.". Nothing is saved, nobody is waitlisted, and events no longer have a waiting-list setting.
- **Automated:** `test_full_event_is_blocked_with_this_event_is_full`

**TC-45-18 · Other reasons are reported before "full"** *(changed: was "a waiting list does not get around other rules")*
- **Traces to:** AC4, AC5 · **Type:** Negative · **Depends on:** A10
- **Steps:** With E2 full, make it closed (now at the closing time), then disabled, then `confirmed` instead of approved, and register each time.
- **Expected result:** HTTP 409 with `closed`, `disabled` and `not_approved`, each with its own message. Nothing is saved.
- **Automated:** `test_other_reasons_are_reported_before_full`

**TC-45-19 · The last place taken by someone else** *(changed: the exact message)*
- **Traces to:** AC4 · **Type:** Negative
- **Steps:** As farah, register for E3 (one place, taken by ivy).
- **Expected result:** HTTP 409 with reason `full` and exactly "This event is full.". Nothing is saved.
- **Automated:** `test_full_after_the_last_place_is_taken`

## AC5 — Closed or disabled says which

**TC-45-20 · Each reason has its own message, and closed and disabled say which** *(changed)*
- **Traces to:** AC4, AC5 · **Type:** Negative
- **Steps:** Get the blocked response for each reason: `not_approved` (E1 as `submitted`), `disabled` (E4), `not_open_yet` (E5), `closed` (E6) and `full` (E3).
- **Expected result:** Five different, non-empty messages. The disabled one says registration has not been enabled; the closed one says registration is closed; the not-yet-open one says when it opens. Nothing is saved.
- **Automated:** `test_each_reason_has_its_own_message`

## AC6 — Saving fails

**TC-45-21 · Save fails: nothing is created, retry works**
- **Traces to:** AC6 · **Type:** Negative (failure)
- **Preconditions:** The commit raises `SQLAlchemyError`.
- **Steps:** As farah, register for E1. Then retry with the database working.
- **Expected result:** HTTP 503 with `retryable: true`, saying the registration was not saved and to try again. No registration exists. The retry gives HTTP 201.
- **Automated:** `test_failed_save_creates_nothing_and_retry_works`

## Concurrency (manual)

**TC-45-22 · Two attendees take the last place at the same time**
- **Traces to:** AC1, AC2, AC4 · **Type:** Concurrency · **Automated:** no. The test suite's rows are never committed, so a second connection cannot see them.
- **Steps:** Against a scratch event with one place left, send two registrations from different attendees at the same moment (e.g. two `curl` calls in parallel). Then send two from the same attendee at once.
- **Expected result:** Exactly one attendee is `registered`; the other gets `full`. The same attendee ends up with one registration, and both responses show it.

## Frontend

**TC-45-23 · Register page** *(changed: no Waitlisted status)*
- **Traces to:** AC2–AC6 · **Type:** Frontend
- **Page:** `/events/:eventId/register`, sending `POST /registrations/` with `{"event_id": <id>}`.
- **Expected result:**
  - The Register button is disabled while the request is sent, so a double click sends one request.
  - On success, the confirmation message and "Status: Registered" are shown, and the button is gone. An existing registration is shown the same way.
  - A blocked registration shows the server's message as an alert ("This event is full.", "Registration for this event is closed." or "Registration has not been enabled for this event.") and no status.
  - A failed save shows the server's message and leaves the button enabled to retry. A network failure shows a fallback message.
- **Automated:** `EventRegistrationPage.test.jsx`

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 22 |
| AC2 | 01, 11, 16, 22, 23 |
| AC3 | 12, 14, 15, 16, 23 |
| AC4 | 06, 17, 18, 19, 20, 22, 23 |
| AC5 | 03, 04, 05, 07, 18, 20, 23 |
| AC6 | 21, 23 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 11 |
| Negative | 02, 03, 05, 07, 08, 10, 12, 16, 17, 18, 19, 20, 21 |
| Boundary | 04, 06, 09, 14, 15 |
| Cross-cutting (authorisation) | 08, 09, 10 |
| Concurrency (manual) | 22 |
| Frontend | 23 |
| Retired | 13 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Can only attendees register, or also organisers, coordinators and staff (e.g. for someone else's event)? Can an attendee register someone else? Assumed: attendees only, for themselves. | A1, TC-45-08, 09 |
| Q2 | ~~What is a "Confirmed" event?~~ **Answered on reopening (18 Oct 2026):** registration needs Approved. | A2, TC-45-02 |
| Q3 | Is "registration enabled" the organiser's "Attendee registration needed" answer (assumed), or a separate switch the coordinator controls? | A3, TC-45-03 |
| Q4 | Who sets the registration period, and is it required? Should registration close automatically when the event starts? Assumed: two recorded times; missing means closed. | A4, TC-45-04, 05 |
| Q5 | Where does the number of places come from: a separate capacity (assumed), the expected attendance, or the venue's capacity? What happens if it isn't set? | A5, TC-45-06, 07 |
| Q6 | ~~Does the waiting list have a limit?~~ **Answered on reopening:** there is no waiting list. Should attendees who were on one be told it was removed? Assumed not; their entries are cancelled. | A6 |
| Q7 | Can an attendee who withdrew or was cancelled register again? Assumed yes. | A7, TC-45-15 |
| Q8 | Should a confirmation email or in-app notification be sent? Assumed not in this story. | A12 |
| Q9 | Once an event is approved, can its capacity and registration period be changed directly, or only through a change request (SCRUM-52)? | Implementation |
