# SCRUM-68 — Event Withdrawal: Test Cases

**User story:** As an Attendee, I want to withdraw from an event I registered for, so that I can free my place when I can no longer attend.

**Created:** 13 Oct 2026 · **Status of all cases:** Written test-first (TDD, red). Nothing is implemented yet, so the automated tests fail until the feature is built, except TC-68-13, which also guards the existing registration endpoint. · **Automated tests:** `backend/tests/test_event_withdrawal.py`, `frontend/src/pages/MyRegistrationsPage.test.jsx` · **Endpoints:** `GET /api/registrations/` (replaces the stub) and `POST /api/registrations/<id>/withdraw` · **Related:** SCRUM-45 (registering; owns `Registration`), SCRUM-74 (slots remaining on the event page)

**Source:** the team's "Sprint 2 test cases" sheet (IS212-US68-TC1 to TC16). Case `TC-68-nn` automates sheet case `IS212-US68-TCn`. Sheet users and events map to the seed data below: attendee_dan is farah and attendee_eve is ivy; the sheet's events E-201 to E-207 are E1 to E7.

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | A signed-in attendee can see only their own registrations, and has no way to view or withdraw another user's registration. |
| AC2 | Each registration shows a "Withdraw" action at any time until the event starts. |
| AC3 | Clicking Withdraw shows a confirmation step; cancelling it leaves the registration unchanged. |
| AC4 | Confirming withdrawal changes the registration's status to "Withdrawn" (it is not deleted) and shows a success message. |
| AC5 | The event's registered count goes down by one and the freed place is available to other attendees. |
| AC6 | Withdrawn registrations no longer appear among active registrations but stay visible in the attendee's history with status "Withdrawn". |
| AC7 | Withdrawing from an event that has started, ended or been cancelled is rejected with a clear message. |
| AC8 | Withdrawing an already-withdrawn registration is rejected (no double decrement). |
| AC9 | The attendee can register again after withdrawing, if there is room. |
| AC10 | If the event has a waiting list, the attendee who has waited longest is given the freed place. |
| AC11 | If withdrawal fails, the registration is unchanged and the user is told. |
| AC12 | Signed-out users are sent to the sign-in page. |

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Who may use it:** attendees only, checked against the database on every request (the SCRUM-45 rule). Other roles get HTTP 403. Withdrawing someone else's registration is also HTTP 403, with a message that does not name the event or the owner. An unknown registration is 404. *(Q1)*
- **A2 — Status:** a new `Registration.status` value, `withdrawn`, beside `registered`, `waitlisted` and `cancelled`. The column is a plain `varchar(20)`, so there is no schema change; the model's comment is updated. `withdrawn` is not active, so the one-active-registration index lets the attendee register again. `cancelled` stays as it is (set by a later story) and is also shown in the history.
- **A3 — My registrations:** `GET /api/registrations/` returns `active` (registered and waitlisted, soonest event first) and `history` (every other status). A `message` is set only when both are empty. Each entry carries `can_withdraw`, so the page does not repeat the server's rules.
- **A4 — Withdraw cut-off (confirmed 13 Oct 2026):** allowed at any time until the event starts. Half-open: allowed at start − 1 minute, refused at the start time. "Now" is `app.registrations.routes.singapore_now()`. A registration on the waiting list can also be withdrawn.
- **A5 — Refusals:** HTTP 409 with a plain message and a `reason`: `already_withdrawn`, `event_cancelled`, or `event_started` (the event has started or ended). Nothing changes. *(Q2)*
- **A6 — Count and places:** only `registered` takes a place. The response returns the event's `registered_count` and `slots_remaining`. Withdrawing from the waiting list frees no place.
- **A7 — History:** a withdrawn registration is kept with its original `registered_at`; no row is deleted or rewritten.
- **A8 — Registering again:** a `withdrawn` registration does not count as active, so the existing `POST /api/registrations/` creates a new row if there is room, and refuses with `full` if there is none. The history then holds both rows. *(Q4)*
- **A9 — Waiting list:** if a `registered` place is freed and the event has `waitlisted` registrations, the one with the earliest `registered_at` (then the lowest ID) becomes `registered` in the same save. They get an in-app `Notification` (kind `registration_promoted`, naming the event) and a queued email; an email failure is not fatal. Nothing about the promoted attendee is sent to the person withdrawing. Withdrawing a waiting-list place promotes nobody. This follows the waiting list SCRUM-45 added; the customer has not said whether people are promoted automatically or offered the place. *(Q5)*
- **A10 — Concurrency:** the event row is locked while counting and promoting (as SCRUM-45 does), so two withdrawals cannot promote the same person. A second withdrawal of the same registration gets `already_withdrawn`.
- **A11 — Saving fails:** HTTP 503 with `retryable: true`; the registration, the count and the waiting list are unchanged and nothing is sent. A failed load of the list is also a 503, never an empty list.
- **A12 — Page and sign-in:** a new `MyRegistrationsPage` at `/my-registrations` (with a nav link) replaces the `RegistrationsPage` stub, whose code breaks when the list's shape changes. Withdrawing needs a confirmation dialog. Pages treat an HTTP 401 as signed out and go to `/login`. *(Q6)*

## Endpoints under test

- `GET /api/registrations/`:
  - **200** `{"active": [entry], "history": [entry], "message": str or null}`.
  - **401**, **403** `{"error": str}`; **503** `{"error": str, "retryable": true}`.
- `POST /api/registrations/<id>/withdraw`:
  - **200** `{"message": str, "registration": {"id", "event_id", "status", "registered_at"}, "event": {"id", "registered_count", "slots_remaining"}}`.
  - **409** `{"error": str, "reason": "already_withdrawn" | "event_cancelled" | "event_started"}`.
  - **401**, **403**, **404**, **503** as above.
- An entry is `{"id", "event": {"id", "title", "start_time", "end_time", "status"}, "status", "registered_at", "can_withdraw"}`.

## What the implementation needs

- `Registration.status` documents `withdrawn` (model comment only; no SQL script and no `test_role.sql` change).
- In `app/registrations/routes.py`: replace the `list_registrations` stub, add the withdraw route, `PROMOTION_NOTIFICATION = "registration_promoted"` as a named constant with a comment, and reuse `_require_attendee`, `singapore_now` and the event lock.
- `frontend/src/pages/MyRegistrationsPage.jsx` with the route `/my-registrations`; remove `RegistrationsPage.jsx` and point its route and nav link at the new page. Update `test_routes.py`: `GET /api/registrations/` is no longer a stub, so it leaves `COLLECTION_ENDPOINTS`, and the withdraw route joins `ALL_ROUTES`.

## Seed data (WD-SEED)

"Now" is fixed at **13 Oct 2026 12:00** Singapore time. Users come from `backend/tests/seed_data.py`, plus extra attendees `ivy`, `jon` and `kim`. Every event is organised by dana and coordinated by alice.

Unless the table says otherwise, an event is `confirmed`, runs 20 Nov 2026 10:00 – 12:00, takes registrations from 1 Oct 2026 09:00 to 19 Nov 2026 00:00, has 5 places and no waiting list.

| Ref | Title | Differs from the defaults | Registrations already made (oldest first) |
|-----|-------|---------------------------|-------------------------------------------|
| E1 | Chem Open House | — | farah, jon registered |
| E2 | Biology Fair | 25 Nov 2026 | ivy registered |
| E3 | Ongoing Workshop | started 13 Oct 2026 09:00, ends 17:00 | farah registered |
| E4 | Cancelled Concert | status `cancelled` | farah registered |
| E5 | Robotics Day | — | farah withdrawn |
| E6 | Full Gala | 2 places | farah, jon registered (full) |
| E7 | Waitlist Night | 2 places, waiting list on | farah, jon registered; ivy, then kim, waitlisted |
| E8 | Past Seminar | 1 Sep 2026 10:00 – 12:00 | farah registered |

The signed-in attendee is farah unless a case says otherwise. The sheet uses capacity 30 and 10 registered; the seed uses smaller numbers so the cases stay fast.

---

## AC1 — My registrations, and only mine

**TC-68-01 · The list shows only my registrations** *(sheet TC1)*
- **Traces to:** AC1 · **Type:** Happy path
- **Steps:** As ivy, `GET` the list. As farah, `GET` the list. As a new attendee, `GET` the list.
- **Expected result:** Ivy sees exactly her two registrations (E2 and E7), with the entries' fields, and no registration of farah's or jon's. Farah sees exactly her own, soonest event first. The new attendee gets empty lists and a message that says they have no registrations. The page lists each registration with its event, start time ("Starts: 20/11/2026 10:00 SGT") and status, shows the server's message when there are none, and goes to `/login` when signed out.
- **Automated:** `MyRegistrationsTests.test_list_shows_only_the_signed_in_attendees_registrations`, `test_active_registrations_are_listed_soonest_first`, `test_no_registrations_gives_a_message`; frontend: "lists the attendee's active registrations with their event, start time and status", "shows the server's message when there are no registrations".

**TC-68-02 · Nobody can withdraw someone else's registration** *(sheet TC2)*
- **Traces to:** AC1 · **Type:** Negative (authorisation) · **Depends on:** Q1
- **Steps:** As farah, withdraw ivy's registration for E2. As admin, dana, alice and gus, `GET` the list and withdraw farah's registration. As farah, withdraw a registration ID that does not exist.
- **Expected result:** HTTP 403 for the first two (the message names neither the event nor ivy), and ivy's registration is still `registered` and still listed. HTTP 404 for the unknown ID. Nothing changes.
- **Automated:** `MyRegistrationsTests.test_attendee_cannot_withdraw_another_attendees_registration`, `test_other_roles_and_unknown_registrations`; frontend: "shows the server's message for a 403 and leaves the registration as it was".

## AC2 — When Withdraw is offered

**TC-68-03 · Withdraw is offered before the event starts** *(sheet TC3)*
- **Traces to:** AC2 · **Type:** Happy path
- **Steps:** As farah, read the entry for E1. As ivy, read her waiting-list entry for E7.
- **Expected result:** `can_withdraw: true` for both. The page shows a "Withdraw from Chem Open House" button next to the registration.
- **Automated:** `WithdrawActionTests.test_withdraw_is_offered_before_the_event_starts`; frontend: "offers Withdraw only where the server says withdrawing is possible".

**TC-68-04 · Withdraw is not offered once the event has started** *(sheet TC4)*
- **Traces to:** AC2 · **Type:** Negative, boundary · **Depends on:** Q2
- **Steps:** As farah, read the entries for E3 (started today at 09:00), E8 (ended) and E4 (cancelled). Then, for E1 (starts 20 Nov 10:00), set now to 09:59 and to 10:00 and read the entry.
- **Expected result:** `can_withdraw: false` for E3, E8 and E4. For E1, `true` at 09:59 and `false` at 10:00. The page shows no Withdraw button where `can_withdraw` is false, but still lists the registration.
- **Automated:** `WithdrawActionTests.test_withdraw_is_not_offered_once_the_event_has_started`, `test_withdraw_cut_off_is_the_start_time`; frontend: "offers Withdraw only where the server says withdrawing is possible".

## AC3, AC4 — Confirming a withdrawal

**TC-68-05 · Cancelling the confirmation keeps the registration** *(sheet TC5)*
- **Traces to:** AC3 · **Type:** Negative · **Automated:** frontend only; the server sees no request.
- **Steps:** On the page, click "Withdraw from Chem Open House", then Cancel in the dialog.
- **Expected result:** The dialog names the event, then closes. No request is sent. The registration is still listed as Registered, with its Withdraw button.
- **Automated:** frontend: "asks for confirmation first, and cancelling leaves the registration unchanged".

**TC-68-06 · Confirmed withdrawal sets the status to Withdrawn** *(sheet TC6)*
- **Traces to:** AC4 · **Type:** Happy path
- **Steps:** As farah, withdraw from E1.
- **Expected result:** HTTP 200 with a message naming "Chem Open House" and the registration with status `withdrawn` and the same ID. The row still exists (one row for farah and E1), with its original `registered_at`. The page sends `POST /registrations/<id>/withdraw` once, shows the message, and moves the registration to the history as "Status: Withdrawn" without a Withdraw button; Confirm is disabled while sending, so a double click sends one request.
- **Automated:** `WithdrawTests.test_confirmed_withdrawal_sets_status_to_withdrawn`; frontend: "withdraws on confirmation, shows the success message and moves the registration to the history", "sends one request when Confirm is clicked twice".

## AC5 — Count and places

**TC-68-07 · The registered count goes down by one** *(sheet TC7)*
- **Traces to:** AC5 · **Type:** Happy path
- **Steps:** As farah, withdraw from E1 (2 registered, 5 places). As ivy, leave E7's waiting list.
- **Expected result:** E1: `registered_count` 1 and `slots_remaining` 4, jon still registered. E7's waiting list: the registered count stays 2 and slots remaining 0, because a waiting-list place frees nothing.
- **Automated:** `WithdrawTests.test_registered_count_and_slots_update`, `test_leaving_the_waiting_list_does_not_change_the_count`.

**TC-68-08 · A freed place on a full event can be taken** *(sheet TC8)*
- **Traces to:** AC5 · **Type:** Happy path (integration with SCRUM-45)
- **Steps:** E6 is full with no waiting list. As ivy, register for E6. As farah, withdraw from E6. As ivy, register again.
- **Expected result:** The first attempt gets HTTP 409, reason `full`. After the withdrawal, ivy gets HTTP 201 and status `registered`, and E6 is full again with 2 registered.
- **Automated:** `WithdrawTests.test_freed_place_on_a_full_event_can_be_taken`.

## AC6 — History

**TC-68-09 · A withdrawn registration moves to the history** *(sheet TC9)*
- **Traces to:** AC6 · **Type:** Happy path
- **Steps:** As farah, `GET` the list (her E5 registration is already withdrawn). Withdraw from E1. `GET` the list again.
- **Expected result:** Before: E1 is active and the history holds only E5. After: E1 is not active; the history holds E5 and E1, and E1's entry has status `withdrawn`, its event title and `can_withdraw: false`. An already-withdrawn entry never offers Withdraw. The page lists history entries in a History section without buttons.
- **Automated:** `WithdrawTests.test_withdrawn_registration_moves_to_the_history`, `WithdrawActionTests.test_withdrawn_registration_has_no_withdraw_action`; frontend: "shows withdrawn registrations in the history, with no Withdraw button".

## AC7, AC8 — Refused withdrawals

**TC-68-10 · An event that has started or ended** *(sheet TC10)*
- **Traces to:** AC7 · **Type:** Negative, boundary · **Depends on:** Q2
- **Steps:** As farah, withdraw from E3 (started) and E8 (ended). Then set now to 09:59 on E1's start day and withdraw farah; set now to exactly the start time and withdraw jon.
- **Expected result:** E3 and E8: HTTP 409, reason `event_started`, with a message about the event having started or ended; the registration is still `registered` and nobody is promoted. E1 at 09:59: HTTP 200. E1 at the start time: HTTP 409 and jon is still registered.
- **Automated:** `RefusedWithdrawalTests.test_withdrawal_after_the_event_has_started_is_rejected`, `test_withdrawal_boundary_is_the_start_time`; frontend: "shows the server's message for a 409 and leaves the registration as it was".

**TC-68-11 · A cancelled event** *(sheet TC11)*
- **Traces to:** AC7 · **Type:** Negative
- **Steps:** As farah, withdraw from E4.
- **Expected result:** HTTP 409, reason `event_cancelled`, a message mentioning "cancelled". The registration is still `registered`.
- **Automated:** `RefusedWithdrawalTests.test_withdrawal_from_a_cancelled_event_is_rejected`.

**TC-68-12 · A second withdrawal of the same registration** *(sheet TC12)*
- **Traces to:** AC8 · **Type:** Negative (stale page, double submit)
- **Steps:** As farah, withdraw from E1 twice in a row (the second is what a stale second tab sends).
- **Expected result:** The second gets HTTP 409, reason `already_withdrawn`, a message mentioning "already". E1's registered count is 1 (jon only), not 0. The page shows the server's message and leaves the list as it was.
- **Automated:** `RefusedWithdrawalTests.test_second_withdrawal_is_rejected_without_a_second_decrement`; frontend: "shows the server's message for a 409 and leaves the registration as it was".

## AC9 — Registering again

**TC-68-13 · The attendee can register again after withdrawing** *(sheet TC13)*
- **Traces to:** AC9 · **Type:** Happy path · **Depends on:** Q4
- **Steps:** Farah's E5 registration is already withdrawn. As farah, register for E5. Then, with farah's registration still withdrawn, fill E5's five places with other attendees and register again.
- **Expected result:** The first gets HTTP 201 with status `registered`, and farah now has two rows for E5 (`withdrawn`, then `registered`). The second gets HTTP 409, reason `full`, and the withdrawn row is unchanged. This case passes against today's registration endpoint; it guards against `withdrawn` ever being treated as active.
- **Automated:** `RegisterAgainTests.test_attendee_can_register_again_after_withdrawing`, `test_registering_again_still_needs_a_free_place`.

## AC10 — Waiting list

**TC-68-14 · The longest-waiting attendee gets the freed place** *(sheet TC14)*
- **Traces to:** AC10 · **Type:** Happy path · **Depends on:** Q5
- **Steps:** On E7 (full, ivy then kim waiting), farah withdraws. Then swap the waiting times so kim joined first, and withdraw again. Then ivy leaves the waiting list. Then withdraw from E6, which has nobody waiting. Then withdraw from E7 with the email queue raising an error.
- **Expected result:** Ivy becomes `registered`, kim stays `waitlisted`; ivy gets one in-app notification (kind `registration_promoted`, naming "Waitlist Night") and one email to her address; farah's response contains neither ivy's nor kim's email. With the times swapped, kim is promoted, not ivy: the order is how long they waited, not the row number. When ivy leaves the list, nobody is promoted and nothing is sent. With nobody waiting, nobody is promoted. With the queue down, the withdrawal and promotion are still saved.
- **Automated:** `WaitingListTests.test_first_waitlisted_attendee_gets_the_freed_place`, `test_waiting_list_order_is_by_time_waiting`, `test_leaving_the_waiting_list_promotes_nobody`, `test_nobody_waiting_means_nobody_is_promoted`, `test_email_queue_failure_is_not_fatal`.

## AC11 — Saving fails

**TC-68-15 · A save failure leaves the registration unchanged** *(sheet TC15)*
- **Traces to:** AC11 · **Type:** Negative (failure)
- **Preconditions:** The commit raises `SQLAlchemyError`. In a third test, loading the user raises it.
- **Steps:** As farah, withdraw from E1; retry with the database working. Withdraw from E7 with the commit failing. `GET` the list with loading failing.
- **Expected result:** HTTP 503 with `retryable: true`, a message that says to try again, without the database error. Farah is still `registered` and the count is still 2; the retry gives HTTP 200 and a count of 1. On E7 nobody is promoted, no notification is saved and no email is queued. A failed load is a 503 with `retryable: true`, not an empty list. The page shows the server's message, keeps the registration with its Withdraw button enabled and succeeds on the second try; a network failure shows a fallback message; a list that could not be loaded offers Retry.
- **Automated:** `SaveFailureTests.test_failed_save_leaves_the_registration_unchanged`, `test_failed_save_promotes_nobody`, `test_failed_load_is_reported_as_a_failure`; frontend: "shows an error when saving fails, keeps the registration and lets the attendee try again", "shows a fallback message when the server cannot be reached", "shows why the list could not be loaded and lets the attendee try again".

## AC12 — Signed out

**TC-68-16 · Signed-out users are sent to sign in** *(sheet TC16)*
- **Traces to:** AC12 · **Type:** Negative (authentication)
- **Steps:** `GET` the list and withdraw farah's E1 registration with no token, an expired token and the token of a deleted user.
- **Expected result:** HTTP 401 every time; the registration is still `registered`. The page goes to `/login` and shows no registrations.
- **Automated:** `SignedOutTests.test_signed_out_users_get_401`; frontend: "sends a signed-out user to the sign-in page and shows no registrations".

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02 |
| AC2 | 03, 04 |
| AC3 | 05 |
| AC4 | 06 |
| AC5 | 07, 08 |
| AC6 | 09 |
| AC7 | 04, 10, 11 |
| AC8 | 12 |
| AC9 | 13 |
| AC10 | 14 |
| AC11 | 15 |
| AC12 | 16 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 03, 06, 07, 08, 09, 13, 14 |
| Negative | 02, 04, 05, 10, 11, 12, 15, 16 |
| Boundary | 04, 10 |
| Cross-cutting (authorisation) | 02 |
| Cross-cutting (authentication) | 16 |
| Frontend only | 05 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Can anyone other than the attendee withdraw a registration, e.g. an organiser or admin removing someone? Assumed: no. | A1, TC-68-02 |
| Q2 | Is the cut-off the event's start time (assumed, confirmed 13 Oct 2026)? Should there be a fee or penalty for late withdrawal? | A4, A5, TC-68-04, 10 |
| Q3 | Should the attendee get a confirmation email or notification of their own withdrawal? Assumed: no, the on-screen message is enough. | A9 |
| Q4 | Can an attendee register again after withdrawing? Assumed: yes, if there is room. | A8, TC-68-13 |
| Q5 | When a place frees up and people are waiting, are they moved up automatically (assumed) or offered the place and given time to accept? Is the first in line promoted? | A9, TC-68-14 |
| Q6 | Should the history keep every withdrawal, or only the latest per event? Assumed: every one. | A7, A12 |
