# SCRUM-45 — Register for an Event: Test Cases

**User story:** As an Attendee, I want to register for an event so that I can secure my place.

**Created:** 9 Oct 2026 · **Status of all cases:** Automated cases pass (9 Oct 2026, Supabase with db/event_registration.sql applied + Vitest); TC-45-22 is checked manually. · **Automated tests:** `backend/tests/test_event_registration.py`, `frontend/src/pages/EventRegistrationPage.test.jsx` · **Endpoint:** `POST /api/registrations/` (the existing stub) · **Related:** SCRUM-29 (`registration_required`), SCRUM-52/53 (which event fields can be edited directly)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | I can register only if the event status is "Confirmed", registration is enabled and within its registration period, and places are available. |
| AC2 | On success, exactly one active registration is created and linked to me, and a confirmation message is shown. |
| AC3 | If I already have an active registration, no second one is created and my existing status is shown instead. |
| AC4 | If the event is full and has an active waiting list, I'm added to the waiting list and told my status is "Waitlisted". |
| AC5 | If registration is closed, disabled, or the event is full without a waiting list, registration is blocked and a clear message explains why. |
| AC6 | If saving fails, no registration is created and an error message is shown. |

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Who registers:** only users whose role is `attendee`, checked against the database on every request. Organisers, coordinators, staff and admins get HTTP 403. An attendee registers only themselves. *(Q1)*
- **A2 — "Confirmed":** a new event status, `confirmed`, that comes after `approved` and is set by a later story. Events in any other status (`draft`, `submitted`, `under_review`, `approved`, `rejected`, `cancelled`) do not accept registrations. The refusal does not reveal the event's title or status, because attendees should not learn about requests that are not public. *(Q2)*
- **A3 — Registration enabled:** `Event.registration_required` (SCRUM-29's "Attendee registration needed") is `true`. `false` or not recorded means registration is disabled. *(Q3)*
- **A4 — Registration period:** two new event columns, `registration_opens_at` and `registration_closes_at`, in Singapore time without a time zone, like the event's own times. Registration is open from the opening time up to, but not including, the closing time, the same half-open rule as venue scheduling. If either is not recorded, registration is closed. "Now" is the current Singapore time. *(Q4)*
- **A5 — Places:** a new event column, `registration_capacity`, gives the number of places. Only `registered` registrations take a place; `waitlisted` and `cancelled` ones do not. If the capacity is not recorded, registration is treated as disabled. Neither `expected_attendance` (the organiser's estimate) nor the venue's capacity is used for this. *(Q5)*
- **A6 — Waiting list:** a new event column, `waitlist_enabled`, marks an active waiting list. When every place is taken and it is `true`, the attendee is added with status `waitlisted`. The list has no length limit. Moving people off the waiting list when a place frees up is a separate story. A waiting list does not get around any other rule: a closed, disabled or unconfirmed event still blocks. *(Q6)*
- **A7 — Active registration:** a new `Registration.status` column holds `registered`, `waitlisted` or `cancelled`. "Active" means `registered` or `waitlisted`. A partial unique index on `(event_id, attendee_id)` for active rows lets the database guarantee one active registration per attendee per event. A cancelled registration (cancelling is a later story) does not count, so that attendee can register again with a new row. *(Q7)*
- **A8 — Already registered:** if the attendee already has an active registration, the response is HTTP 200 with that registration unchanged, `already_registered: true`, and a message giving the existing status. This happens **before** the eligibility checks, so an attendee who registered while places were available still sees their status after the event fills or registration closes.
- **A9 — Blocked:** HTTP 409 with a plain message and a machine-readable `reason`: `not_confirmed`, `disabled`, `not_open_yet` (the message says when registration opens), `closed`, or `full` (no waiting list). Each reason has its own message. Nothing is saved.
- **A10 — Order of checks:** not logged in (401) → not an attendee (403) → invalid body (400) → unknown event (404) → existing active registration (200) → not confirmed → disabled → before the period → after the period → full without a waiting list (409). The role check comes before the event lookup, so other users cannot probe which event IDs exist.
- **A11 — Saving fails:** HTTP 503 with `retryable: true`, saying the registration was not saved and to try again. No row is created, and a retry works once the database is back.
- **A12 — No email:** the confirmation is the response message. No notification or email is sent in this story. *(Q8)*

## Endpoint under test

- `POST /api/registrations/` with body `{"event_id": int}`:
  - **201** `{"message": str, "registration": registration}`: registered or waitlisted.
  - **200** `{"message": str, "registration": registration, "already_registered": true}`: existing active registration.
  - **409** `{"error": str, "reason": str}`: blocked (A9).
  - **400**, **401**, **403**, **404** `{"error": str}`.
  - **503** `{"error": str, "retryable": true}`.
- A registration is `{"id", "event_id", "status", "registered_at"}`. `status` is `registered` or `waitlisted`, and `registered_at` is naive UTC.

## What the implementation needs

- `Event`: `registration_opens_at` and `registration_closes_at` (DateTime, Singapore time), `registration_capacity` (Integer), `waitlist_enabled` (Boolean). All nullable with no defaults, because NULL means not recorded.
- `Registration.status` (String(20), not null, default `registered` so existing rows stay active), plus a partial unique index on `(event_id, attendee_id) where status in ('registered', 'waitlisted')`.
- `db/event_registration.sql` with these changes. No new tables, so `db/test_role.sql` need not be re-run.
- `app.registrations.routes.singapore_now()` returns the current Singapore time without a time zone. The tests patch it to fix "now".
- The event row is locked (`SELECT … FOR UPDATE`) while places are counted, so two attendees cannot both take the last place (TC-45-21). An `IntegrityError` from the unique index (the same attendee registering twice at once) returns the existing registration instead of failing.
- `confirmed` is added to `frontend/src/utils/statusLabel.js`. Each new event column is classified as a normal or restricted field for SCRUM-53/52, or left non-editable *(Q9)*.

## Seed data (RG-SEED)

"Now" is fixed at **1 Nov 2026 12:00** Singapore time. Users come from `backend/tests/seed_data.py`, plus two extra attendees, `ivy` and `jon`. Every event is organised by dana, coordinated by alice, and runs 12 Dec 2026 17:00 – 22:00.

Unless the table says otherwise, an event has status `confirmed`, registration enabled, opens 1 Oct 2026 09:00, closes 1 Dec 2026 00:00, and no waiting list.

| Ref | Title | Capacity | Differs from the defaults | Registrations already made |
|-----|-------|----------|---------------------------|----------------------------|
| E1 | Harbour Lights Festival | 3 | — | none |
| E2 | Winter Networking Night | 2 | waiting list on | ivy, jon registered (full) |
| E3 | Product Launch | 1 | — | ivy registered (full) |
| E4 | Rooftop Cinema | 50 | registration disabled | none |
| E5 | Spring Garden Party | 50 | opens 15 Nov 2026 09:00 | none |
| E6 | Alumni Mixer | 50 | closed 1 Nov 2026 00:00 | none |
| E7 | Tech Summit | not recorded | — | none |

The registering attendee is `farah` unless a case says otherwise.

---

## AC1 — Who can register, and for which events

**TC-45-01 · Register for a confirmed, open event with places**
- **Traces to:** AC1, AC2 · **Type:** Happy path
- **Steps:** As farah, register for E1.
- **Expected result:** HTTP 201 with status `registered` and a confirmation message naming "Harbour Lights Festival".

**TC-45-02 · Only confirmed events accept registrations**
- **Traces to:** AC1, AC5 · **Type:** Negative (business rule) · **Depends on:** Q2
- **Steps:** Set E1's status to each of `draft`, `submitted`, `under_review`, `approved`, `rejected` and `cancelled` in turn, and register.
- **Expected result:** HTTP 409 with reason `not_confirmed` each time. The message does not contain the event's title or status. No registration is created.

**TC-45-03 · Registration disabled**
- **Traces to:** AC1, AC5 · **Type:** Negative · **Depends on:** Q3
- **Steps:** Register for E4. Then set E4's `registration_required` to not recorded and register again.
- **Expected result:** HTTP 409 with reason `disabled` both times. Nothing is saved.

**TC-45-04 · Registration period boundaries**
- **Traces to:** AC1, AC5 · **Type:** Boundary · **Depends on:** Q4
- **Test data (E1, opens 1 Oct 2026 09:00, closes 1 Dec 2026 00:00):** now = 1 Oct 08:59 → `not_open_yet`; now = 1 Oct 09:00 → registered; now = 30 Nov 23:59 → registered; now = 1 Dec 00:00 → `closed`. A different attendee registers each time.
- **Expected result:** As listed. The `not_open_yet` message gives the opening date.

**TC-45-05 · Not yet open, or already closed**
- **Traces to:** AC1, AC5 · **Type:** Negative · **Depends on:** Q4
- **Steps:** Register for E5, then E6. Then remove E1's opening time and register; then remove its closing time instead and register.
- **Expected result:** E5 gives `not_open_yet`; E6 and both incomplete periods give `closed`. Nothing is saved.

**TC-45-06 · The last place, and what takes a place**
- **Traces to:** AC1 · **Type:** Boundary · **Depends on:** Q5
- **Preconditions:** E1 (capacity 3) has two `registered`, one `waitlisted` and one `cancelled` registration from other attendees.
- **Steps:** farah registers for E1, then another attendee does.
- **Expected result:** farah is `registered` (waitlisted and cancelled registrations do not take places). The next attendee gets HTTP 409 `full`.

**TC-45-07 · Capacity not recorded**
- **Traces to:** AC1, AC5 · **Type:** Negative · **Depends on:** Q5
- **Steps:** Register for E7.
- **Expected result:** HTTP 409 with reason `disabled`. Nothing is saved.

**TC-45-08 · Only attendees can register**
- **Traces to:** AC1 · **Type:** Negative (authorisation) · **Depends on:** Q1
- **Steps:** Register for E1 as admin, alice, dana, gus and hana. Then, as dana, send an invalid body and an unknown event ID.
- **Expected result:** HTTP 403 every time (the role is checked before the body and the event). Nothing is saved.

**TC-45-09 · Access follows role changes**
- **Traces to:** AC1 · **Type:** Boundary (authorisation)
- **Steps:** Get a token for farah, change her role to organiser, then register for E1 with that token.
- **Expected result:** HTTP 403. Nothing is saved.

**TC-45-10 · A valid session, a valid body and an existing event are required**
- **Traces to:** AC1 · **Type:** Negative
- **Test data:** No token, an expired token and a deleted user's token (401); `event_id` missing, `"1"`, `true`, `1.5` and a body that is not JSON (400); an ID no event has (404).
- **Expected result:** As listed. Nothing is saved.

## AC2 — Exactly one registration, linked to me

**TC-45-11 · The registration is saved and linked to the attendee**
- **Traces to:** AC2 · **Type:** Happy path
- **Steps:** As farah, register for E1.
- **Expected result:** Exactly one new registration exists across the seeded events: E1, farah, status `registered`, with `registered_at` between just before and just after the request. The response's `registration` matches the saved row. Other attendees' registrations are unchanged.

## AC3 — Already registered

**TC-45-12 · Registering twice shows the existing registration**
- **Traces to:** AC3 · **Type:** Negative (duplicate)
- **Steps:** As farah, register for E1 twice.
- **Expected result:** The second call gives HTTP 200, `already_registered: true`, the same registration (same ID and time), and a message saying she is already registered with status "Registered". Only one registration exists.

**TC-45-13 · Already on the waiting list**
- **Traces to:** AC3, AC4 · **Type:** Negative (duplicate)
- **Steps:** farah joins E2's waiting list, then registers for E2 again.
- **Expected result:** HTTP 200 with status `waitlisted` and a message saying "Waitlisted". Still only one registration for farah.

**TC-45-14 · The existing status is shown even after registration closes or fills up**
- **Traces to:** AC3 · **Type:** Boundary · **Depends on:** A8
- **Steps:** ivy (registered for E3, now full) registers for E3 again. farah registers for E1, then E1 is cancelled, its registration is disabled, and the clock moves past its closing time; she registers again.
- **Expected result:** HTTP 200 with the existing registration each time, never 409.

**TC-45-15 · A cancelled registration does not count**
- **Traces to:** AC3 · **Type:** Boundary · **Depends on:** Q7
- **Preconditions:** farah has a `cancelled` registration for E1.
- **Expected result:** Registering gives HTTP 201 with a new `registered` row. The cancelled row is unchanged.

**TC-45-16 · The database allows only one active registration**
- **Traces to:** AC2, AC3 · **Type:** Negative (data integrity)
- **Steps:** Insert a second active registration (`registered` + `registered`, then `registered` + `waitlisted`) for the same attendee and event directly.
- **Expected result:** Each insert fails with an integrity error. A `cancelled` row next to an active one is allowed.

## AC4 — Waiting list

**TC-45-17 · Full with a waiting list: added as Waitlisted**
- **Traces to:** AC4 · **Type:** Happy path · **Depends on:** Q6
- **Steps:** As farah, register for E2.
- **Expected result:** HTTP 201 with status `waitlisted`. The message says the event is full and her status is "Waitlisted". E2 still has exactly two `registered` registrations.

**TC-45-18 · A waiting list does not get around other rules**
- **Traces to:** AC4, AC5 · **Type:** Negative · **Depends on:** Q6
- **Steps:** With E2's waiting list on, make it closed (now after the closing time), then disabled, then `approved` instead of confirmed, and register each time.
- **Expected result:** HTTP 409 with `closed`, `disabled` and `not_confirmed`. Nobody is waitlisted.

## AC5 — Blocked registrations explain why

**TC-45-19 · Full without a waiting list**
- **Traces to:** AC5 · **Type:** Negative
- **Steps:** As farah, register for E3.
- **Expected result:** HTTP 409 with reason `full`. The message says the event is full. Nothing is saved.

**TC-45-20 · Each reason has its own clear message**
- **Traces to:** AC5 · **Type:** Negative
- **Steps:** Get the blocked response for each reason: `not_confirmed` (E1 as `approved`), `disabled` (E4), `not_open_yet` (E5), `closed` (E6) and `full` (E3).
- **Expected result:** Five different, non-empty messages. Nothing is saved.

## AC6 — Saving fails

**TC-45-21 · Save fails: nothing is created, retry works**
- **Traces to:** AC6 · **Type:** Negative (failure)
- **Preconditions:** The commit raises `SQLAlchemyError`.
- **Steps:** As farah, register for E1. Then retry with the database working.
- **Expected result:** HTTP 503 with `retryable: true`, saying the registration was not saved and to try again. No registration exists. The retry gives HTTP 201.

## Concurrency (manual)

**TC-45-22 · Two attendees take the last place at the same time**
- **Traces to:** AC1, AC2 · **Type:** Concurrency · **Automated:** no. The test suite's rows are never committed, so a second connection cannot see them.
- **Steps:** Against a scratch event with one place left, send two registrations from different attendees at the same moment (e.g. two `curl` calls in parallel). Then send two from the same attendee at once.
- **Expected result:** Exactly one attendee is `registered`; the other gets `full` (or `waitlisted` if the waiting list is on). The same attendee ends up with one registration, and both responses show it.

## Frontend

**TC-45-23 · Register page**
- **Traces to:** AC2–AC6 · **Type:** Frontend
- **Page:** `/events/:eventId/register`, sending `POST /registrations/` with `{"event_id": <id>}`.
- **Expected result:**
  - The Register button is disabled while the request is sent, so a double click sends one request.
  - On success, the confirmation message and "Status: Registered" or "Status: Waitlisted" are shown, and the button is gone. An existing registration is shown the same way.
  - A blocked registration shows the server's message as an alert and no status.
  - A failed save shows the server's message and leaves the button enabled to retry. A network failure shows a fallback message.

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 22 |
| AC2 | 01, 11, 16, 22, 23 |
| AC3 | 12, 13, 14, 15, 16, 23 |
| AC4 | 13, 17, 18, 23 |
| AC5 | 02, 03, 04, 05, 07, 18, 19, 20, 23 |
| AC6 | 21, 23 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 11, 17 |
| Negative | 02, 03, 05, 07, 08, 10, 12, 13, 16, 18, 19, 20, 21 |
| Boundary | 04, 06, 09, 14, 15 |
| Cross-cutting (authorisation) | 08, 09, 10 |
| Concurrency (manual) | 22 |
| Frontend | 23 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Can only attendees register, or also organisers, coordinators and staff (e.g. for someone else's event)? Can an attendee register someone else? Assumed: attendees only, for themselves. | A1, TC-45-08, 09 |
| Q2 | What is a "Confirmed" event, and how does it differ from Approved? Which story sets it? Assumed: a new status `confirmed`, after `approved`. | A2, TC-45-02, 18 |
| Q3 | Is "registration enabled" the organiser's "Attendee registration needed" answer (assumed), or a separate switch the coordinator controls? | A3, TC-45-03 |
| Q4 | Who sets the registration period, and is it required? Should registration close automatically when the event starts? Assumed: two recorded times; missing means closed. | A4, TC-45-04, 05 |
| Q5 | Where does the number of places come from: a separate capacity (assumed), the expected attendance, or the venue's capacity? What happens if it isn't set? | A5, TC-45-06, 07 |
| Q6 | Does the waiting list have a limit? Should waitlisted attendees see their position? How are they moved up when a place frees? | A6, TC-45-17, 18 |
| Q7 | Can an attendee who cancelled register again? Assumed yes. | A7, TC-45-15 |
| Q8 | Should a confirmation email or in-app notification be sent? Assumed not in this story. | A12 |
| Q9 | Once an event is confirmed, can its capacity, waiting list and registration period be changed directly, or only through a change request (SCRUM-52)? | Implementation |
