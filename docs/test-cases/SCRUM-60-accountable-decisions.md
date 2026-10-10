# SCRUM-60 — Record Who Decided and When: Test Cases

**User story:** As an Event Coordinator, I want my approval or rejection to be recorded reliably, with who decided and when, so that the decision is accountable and the Event Organiser gets an accurate outcome.

**Created:** 10 Oct 2026 · **Status of all cases:** Automated cases written first (TDD, red) · **Automated tests:** `backend/tests/test_decision_accountability.py`, `frontend/src/pages/ReviewRequestPage.test.jsx`, `frontend/src/pages/MyRequestsPage.test.jsx`, `frontend/src/pages/MyEventRequestsPage.test.jsx` · **Endpoints:** `POST /api/events/<id>/decision`, `GET /api/events/<id>/review`, `GET /api/events/requests`, `GET /api/events/mine` · **Related:** SCRUM-32 (approve or reject, which this story hardens), SCRUM-33 (coordinator assignment), SCRUM-59 (the organiser's combined list)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The decision records the deciding coordinator and the date and time, and these are shown with the outcome. |
| AC2 | A rejection reason made up only of spaces is refused, and the coordinator is told a reason is required. |
| AC3 | After deciding, the coordinator sees a confirmation of the outcome. |
| AC4 | If saving the decision fails, the request's status is unchanged, an error is shown, and any entered rejection reason is kept for retry. |

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Who decided:** the logged-in coordinator who made the decision (`Event.decided_by_id`), shown as their email address, since users have no stored name. It is kept separately from the event's current coordinator, so reassigning the event afterwards never changes who decided. *(Q1)*
- **A2 — When, and where it is shown:** `decided_at` is the server's clock at the moment of the decision, stored as naive UTC (as in SCRUM-32). It is shown with every outcome: on the coordinator's review page and confirmation, on both of the organiser's lists (SCRUM-32 "My requests" and SCRUM-59 "My event requests"), and in the organiser's in-app notification and email. Pages show it in the viewer's local time (as for every other audit time). The notification and email show Singapore time and say so, because they are plain text. A decision saved before the decider was recorded shows "Decided by: not recorded". *(Q2)*
- **A3 — "Only spaces":** a reason is blank if it has no visible character: any mix of ordinary spaces, tabs, line breaks, non-breaking spaces, ideographic spaces and invisible zero-width characters (zero-width space, byte-order mark). The page refuses it before sending, and the API refuses it as well with HTTP 400, `field: "reason"` and the message "A reason is required to reject this request." A reason with visible text is saved with surrounding spaces trimmed. An approval note made only of spaces is saved as no note (SCRUM-32 A3). *(Q3)*
- **A4 — Recorded reliably:** one request gets exactly one decision. The API locks the request's row and re-reads it before deciding, so two decisions sent at the same time (e.g. two tabs, or a double click) cannot both see "submitted": the first is saved, and the second is refused with HTTP 409 and changes nothing. *(Q4)*
- **A5 — Confirmation:** the API reply names the outcome, the event and the organiser who was notified, and returns the saved request with `decided_at` and `decided_by`. The page shows the reply's message together with who decided and when, read from the saved request.
- **A6 — Save failures are reported accurately:** if the save fails, the reply is HTTP 503 with `retryable: true`, nothing is saved (status, decider, time, reason, notification), and no email is queued. The page shows the error and keeps the typed reason exactly as typed so the coordinator can retry. The reverse also holds: once the decision is saved, a problem afterwards (e.g. the database connection dropping before the reply is built) must not be reported as "not saved", because a retry would then be refused as already decided. *(Q5)*
- **A7 — Order of checks:** unchanged from SCRUM-32: 401, 404, 403, 400 (bad decision or blank reason), 409 (not submitted).

## Endpoints under test

- `POST /api/events/<id>/decision` with `{"decision": "approve" | "reject", "reason": str}` → **200** `{"message": str, "request": request, "notification": {"in_app": true, "email_queued": bool}}`. `message` is `You <approved|rejected> "<title>". <organiser email> has been notified.`
- **400** for a blank reason: `{"error": "A reason is required to reject this request.", "field": "reason"}`. **503** `{"error", "retryable": true}` if saving fails.
- `request` (review and decision replies) includes `"decided_at"` and `"decided_by": {"id", "email"} | null` (SCRUM-32).
- **New:** the organiser's list items on `GET /api/events/requests` (`requests`) and `GET /api/events/mine` (`submitted`) also include `"decided_by": {"id", "email"} | null`.

## Seed data (DC-SEED)

The SCRUM-32 seed data, unchanged (see [SCRUM-32](SCRUM-32-approve-reject-event-request.md#seed-data-dc-seed)). The rows used here:

| Ref | Title | Organiser | Coordinator | Status | Decision |
|-----|-------|-----------|-------------|--------|----------|
| R1 | Harbour Lights Festival | dana | alice | submitted | — |
| R5 | Product Launch | dana | alice | approved | by alice, 10 Sep 2026 09:00 UTC, note "Venue confirmed" |
| R6 | Rooftop Cinema | dana | alice | rejected | by alice, 12 Sep 2026 09:00 UTC, reason "No licensed venue is available" |

Users: alice and ben (coordinators), dana (organiser) from `backend/tests/seed_data.py`.

---

## AC1 — Who decided and when is recorded and shown

**TC-60-01 · The decision records the deciding coordinator and the time**
- **Traces to:** AC1 · **Type:** Happy path
- **Steps:** As alice, approve R1. With fresh seed data, reject R1 with a reason. Note the time just before and just after each call.
- **Expected result:** HTTP 200. The saved `decided_by_id` is alice and `decided_at` lies between the two times. The reply's `request.decided_by` is `{"id": alice, "email": alice's email}` and `request.decided_at` equals the saved time.
- **Automated:** `test_decision_records_the_deciding_coordinator_and_time`

**TC-60-02 · Reassigning the event later does not change who decided**
- **Traces to:** AC1 · **Type:** Boundary · **Depends on:** Q1
- **Steps:** alice rejects R1. An admin then reassigns R1 to ben. ben opens R1's review view, and dana lists her requests.
- **Expected result:** Both still show alice as the decider and the original decision time.
- **Automated:** `test_reassigning_the_event_later_does_not_change_who_decided`

**TC-60-03 · The organiser's lists show who decided and when**
- **Traces to:** AC1 · **Type:** Happy path
- **Steps:** As dana, load `GET /api/events/requests` and `GET /api/events/mine`.
- **Expected result:** On both, R6 has `decided_at` `"2026-09-12T09:00:00"` and `decided_by` alice (`{"id", "email"}`), R5 has alice too, and the undecided R1 has `decided_by: null` and `decided_at: null`.
- **Automated:** `test_organisers_lists_show_who_decided_and_when`

**TC-60-04 · The organiser's notification and email name the decider and the time**
- **Traces to:** AC1 · **Type:** Happy path · **Depends on:** Q2
- **Steps:** alice rejects R1 with a reason.
- **Expected result:** dana's in-app notification and the queued email body both contain alice's email and the decision time in Singapore time (saved UTC time + 8 hours), e.g. "12 Sep 2026 at 17:00 (Singapore time)", as well as the reason.
- **Automated:** `test_notification_and_email_name_the_decider_and_the_time`

**TC-60-05 · A second decision sent at the same time cannot overwrite the first**
- **Traces to:** AC1 · **Type:** Negative (concurrency) · **Depends on:** Q4
- **Preconditions:** The test cannot run two database transactions at once (each test runs in one rolled-back transaction), so it simulates the race in two parts.
- **Steps:** 1. Load R1 (status submitted) into the session, then change R1 to "approved by alice" directly in the database, as a decision from a second tab would, without the session seeing it. Then reject R1 as alice. 2. Separately, record the SQL the API runs while deciding R1.
- **Expected result:** 1. HTTP 409. R1 keeps the first decision (approved, its time, its decider) and nobody is notified or emailed for the refused one. 2. The request's row is read with `SELECT … FOR UPDATE`, so in production a concurrent decision waits and then sees the saved one.
- **Automated:** `test_a_decision_made_meanwhile_is_not_overwritten`, `test_the_request_row_is_locked_while_deciding`

## AC2 — A reason made only of spaces is refused

**TC-60-06 · Reasons made only of spaces are refused, and the coordinator is told a reason is required**
- **Traces to:** AC2 · **Type:** Negative · **Depends on:** Q3
- **Test data:** `"     "` (spaces), `" \t\n "` (tabs and line breaks), `"  "` (non-breaking spaces), `"　"` (ideographic space), `"​​"` (zero-width spaces), `"﻿"` (byte-order mark), `" ​ \t"` (mixed).
- **Expected result:** HTTP 400 with `field: "reason"` and the message "A reason is required to reject this request." R1 is unchanged, and nobody is notified or emailed.
- **Automated:** `test_reasons_made_only_of_spaces_are_refused`

**TC-60-07 · A reason with visible text is accepted and trimmed**
- **Traces to:** AC2 · **Type:** Boundary
- **Test data:** `"x"` (one visible character); `"  Venue unavailable 　"`.
- **Expected result:** Both are accepted. They are saved as `"x"` and `"Venue unavailable"`.
- **Automated:** `test_a_reason_with_visible_text_is_accepted_and_trimmed`

## AC3 — The coordinator sees a confirmation

**TC-60-08 · The reply confirms the outcome**
- **Traces to:** AC3 · **Type:** Happy path
- **Steps:** As alice, reject R1 with a reason. With fresh seed data, approve R1.
- **Expected result:** HTTP 200. `message` is `You rejected "Harbour Lights Festival". <dana's email> has been notified.` (or `You approved …`). `request` carries the new status, `decided_at` and `decided_by`.
- **Automated:** `test_the_reply_confirms_the_outcome`

## AC4 — A failed save changes nothing and can be retried

**TC-60-09 · A failed save is reported, changes nothing, and the same reason can be resent**
- **Traces to:** AC4 · **Type:** Negative (failure)
- **Preconditions:** Saving (the commit) raises `SQLAlchemyError` once.
- **Steps:** alice rejects R1 with a reason; the save fails. She sends the same request again.
- **Expected result:** The first call is HTTP 503 with `retryable: true` and says the decision was not saved and to try again. R1's status, decider, time and reason are unchanged, and no notification or email exists. The retry is HTTP 200, and the saved decision has alice as decider and a time from the retry, not from the failed attempt.
- **Automated:** `test_a_failed_save_changes_nothing_and_the_same_reason_can_be_resent`

**TC-60-10 · A saved decision is never reported as failed**
- **Traces to:** AC4 · **Type:** Negative (failure) · **Depends on:** Q5
- **Preconditions:** The commit succeeds, then every further database call fails (connection lost).
- **Steps:** alice rejects R1 with a reason.
- **Expected result:** HTTP 200 with the confirmation and the saved request (status "rejected", alice, the decision time). R1 is saved as rejected, dana's notification exists, and the email is queued.
- **Automated:** `test_a_saved_decision_is_never_reported_as_failed`

## Frontend

**TC-60-11 · The confirmation shows the outcome, who decided and when**
- **Traces to:** AC1, AC3 · **Type:** Frontend
- **Steps:** On R1's review page, reject with a reason; the API replies with the saved request.
- **Expected result:** A status message shows the reply's message and "Decided by <alice's email>" with the decision time in local time. The page shows Status: Rejected and the reason, and the buttons are gone. On an already decided request the page shows the decision time and "Decided by <email>"; when no decider was recorded it shows "Decided by: not recorded".
- **Automated:** `ReviewRequestPage.test.jsx` › "SCRUM-60 …" › "confirms the outcome with who decided and when", "shows who decided an already decided request", "says when the decider was not recorded"

**TC-60-12 · Rejecting with a blank reason says a reason is required**
- **Traces to:** AC2 · **Type:** Frontend · **Depends on:** Q3
- **Test data:** no text, `"   "`, `" \t"`, `"​"`.
- **Expected result:** The Reject button can be pressed. Pressing it shows "A reason is required to reject this request.", marks the reason box as invalid, and sends nothing. Typing a real reason clears the message, and Reject then sends it.
- **Automated:** `ReviewRequestPage.test.jsx` › "says a reason is required when rejecting with only spaces (…)", "clears the message once a reason is typed"

**TC-60-13 · A refused reason from the server is shown and kept**
- **Traces to:** AC2 · **Type:** Frontend
- **Steps:** The API replies 400 `{"error": "A reason is required to reject this request.", "field": "reason"}` (e.g. a character the page did not catch).
- **Expected result:** The message is shown, the typed text is kept, and the status is still Submitted.
- **Automated:** `ReviewRequestPage.test.jsx` › "shows the server's refusal of the reason and keeps the text"

**TC-60-14 · A failed save keeps the reason exactly as typed, and retry resends it**
- **Traces to:** AC4 · **Type:** Frontend
- **Steps:** Type a reason with surrounding spaces and a line break; press Reject; the API replies 503 `retryable: true`. Press Reject again; the API now succeeds.
- **Expected result:** After the failure, the error is shown, the status is still Submitted, the box holds the text exactly as typed, and no confirmation is shown. The retry sends the same trimmed reason, the error disappears and the confirmation appears.
- **Automated:** `ReviewRequestPage.test.jsx` › "keeps the reason exactly as typed after a failed save and resends it on retry"

**TC-60-15 · The organiser's lists show who decided**
- **Traces to:** AC1 · **Type:** Frontend
- **Expected result:** On "My requests" (SCRUM-32) and "My event requests" (SCRUM-59), each decided request shows "Decided by <email>" next to its decision time. A decided request with no recorded decider shows "Decided by: not recorded". Undecided requests show neither.
- **Automated:** `MyRequestsPage.test.jsx` › "SCRUM-60 shows who decided each request"; `MyEventRequestsPage.test.jsx` › "SCRUM-60 shows who decided each submitted request"

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 03, 04, 05, 11, 15 |
| AC2 | 06, 07, 12, 13 |
| AC3 | 08, 11 |
| AC4 | 09, 10, 14 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 03, 04, 08 |
| Negative | 05, 06, 09, 10 |
| Boundary | 02, 07 |
| Cross-cutting (concurrency, failure) | 05, 09, 10 |
| Frontend | 11, 12, 13, 14, 15 |

## Changes to earlier stories' test cases

- **TC-32-20** (SCRUM-32 review page): "Reject is disabled until a reason is typed" becomes "Reject can be pressed, and with no reason the page says a reason is required" (TC-60-12). The SCRUM-32 frontend test is updated to match.
- **TC-32-17** and **TC-59-04**: each listed request now also has `decided_by`. Their exact-payload assertions gain that field. Nothing else about those lists changes.

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Should the decider be shown by email address (assumed, as no names are stored) or by a display name? Should organisers see which coordinator decided at all? Assumed yes, as they can already see their event's coordinator. | A1, TC-60-02, 03 |
| Q2 | In which time zone should the decision time be shown? Assumed: the viewer's local time on pages, and Singapore time (labelled) in notifications and emails. | A2, TC-60-04 |
| Q3 | Should invisible characters (zero-width spaces) count as "spaces"? Assumed yes, since a reason made of them shows nothing to the organiser. | A3, TC-60-06, 12 |
| Q4 | If two decisions arrive together, should the first one win (assumed), or should the coordinator be asked to confirm which one stands? | A4, TC-60-05 |
| Q5 | Should the typed rejection reason also survive a page reload or closed tab (e.g. kept in the browser), or only while the page stays open (assumed)? | A6, TC-60-14 |
| Q6 | Should earlier decisions be kept as a history (e.g. if decisions can later be reversed)? Assumed out of scope: a request has exactly one decision (SCRUM-32 Q2). | A4 |
