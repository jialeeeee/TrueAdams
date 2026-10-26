# SCRUM-31 — Review and Request Clarification on an Event Request: Test Cases

**User story:** As an Event Coordinator, I want to review and send clarification questions to an Event Organiser about their submitted event request so that I can obtain the information needed to continue planning the event.

**Created:** 28 Sep 2026 · **Reopened:** 26 Oct 2026 with AC7–AC10 (starting a review) · **Status of all cases:** TC-31-01 to 25 pass (28 Sep 2026, local PostgreSQL + Vitest); TC-31-14, 15, 18, 21 also to be checked manually in the browser. TC-31-26 to 42 pass (26 Oct 2026, local PostgreSQL built by `ci/build_test_database.py` with `db/event_review_start.sql` applied + Vitest); TC-31-40 to 42 also to be checked manually in the browser · **Automated tests:** `backend/tests/test_event_clarifications.py`, `backend/tests/test_event_review_start.py`, `frontend/src/pages/ClarificationPage.test.jsx`, `frontend/src/pages/ReviewRequestPage.test.jsx`

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The coordinator can send clarification questions (replies) to the organiser of a submitted event request. |
| AC2 | A question is limited to 1,000 words. |
| AC3 | The coordinator is shown that the question was sent successfully. |
| AC4 | If the question could not be sent, the coordinator is shown why, with an actionable error. |
| AC5 | An empty clarification message cannot be sent. |
| AC6 | The Event Organiser is notified when a clarification question is sent. |
| AC7 | Only the assigned coordinator can start a review. Anyone else is denied and nothing changes. *(added on reopening)* |
| AC8 | A Submitted request becomes Under Review, and who and when are recorded. *(added on reopening)* |
| AC9 | A request that is not Submitted cannot be started. *(added on reopening)* |
| AC10 | If saving fails, the status is unchanged and an error is shown. *(added on reopening)* |

The story as written lists "able to reply back (i.e. send questions)" and "able to send questions / replies" as two criteria. They describe the same behaviour, so they are merged into AC1 here (see Q6).

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Who may send:** only the event's current coordinator (`Event.coordinator_id`, set by SCRUM-33), and only while their role is still `coordinator`. This is checked against the database on every request, so a reassignment or role change applies at once, even to a login token issued earlier. An unassigned event must be assigned first. *(Q1)*
- **A2 — Which events:** questions can be sent only while the request is under review: status `submitted` or `under_review`. Drafts (not yet submitted), and cancelled, rejected, approved or completed events, are refused. *(Q2)*
- **A3 — Status:** sending a question does not change the event's status. Status changes belong to the Event Status Management story. *(Q3)*
- **A4 — Word limit:** a word is a run of characters between whitespace (spaces, tabs, new lines). 1 to 1,000 words is allowed; 1,001 or more is refused, and the error states the limit and the number of words entered. *(Q4)*
- **A5 — Empty:** a message that is missing, not text, empty, or only whitespace is empty and is refused. Leading and trailing whitespace is trimmed before saving.
- **A6 — Notification:** the organiser gets an in-app notification, saved together with the question: both are saved, or neither is. An email is then queued through the existing Celery task. If the email cannot be queued, the question still counts as sent (it and the in-app notification are saved), and the response says the email was not queued. *(Q5)*
- **A7 — Who may view the questions:** the event's current coordinator and the event's organiser. Replying to a question is a separate story.
- **A8 — Order of checks:** not logged in (401), unknown event (404), not allowed (403), invalid message (400), event not open for clarification (409). An unknown event is reported before authorisation, as for the existing coordinator endpoints.
- **A9 — Time zone:** saved times are naive UTC, as for `coordinator_assigned_at`.

Added when the story was reopened (26 Oct 2026), agreed with the scrum lead:

- **A10 — Who may start a review:** only the event's current coordinator, the same rule as A1 and as SCRUM-32's review page. Everyone else gets HTTP 403, Leads and administrators included. A request with no coordinator yet can't be started: a Lead assigns it from the queue first (SCRUM-81). *(Q1)*
- **A11 — What is recorded:**
  - The status becomes `under_review`.
  - `review_started_at` (naive UTC) and `review_started_by_id` record when and by whom. They are saved in one commit with the status.
  - The review page shows "Review started by … on …", from the review payload.
  - Neither field can be changed through the normal planning edit (SCRUM-53 TC-53-20).
- **A12 — No notification:** starting a review notifies nobody and sends no email. The organiser sees "Under review" in their request lists. *(Q9)*
- **A13 — Deciding after the review starts:** the coordinator can approve or reject a request that is Submitted **or** Under Review. This was decided by the team on 26 Oct 2026, because otherwise starting a review would block the decision. It changes SCRUM-32/77/78's "Submitted only" rule (SCRUM-77 A1, SCRUM-78 A1, SCRUM-32 Q5). Their cases TC-77-01, 02, 07 and TC-78-01, 02 are updated. A failed decision no longer says the request is "still submitted". *(Q7)*
- **A14 — Questions stay separate:** sending a question doesn't start the review, and A3 is unchanged. Questions can be sent while the request is Submitted or Under Review. *(Q8)*
- **A15 — Order of checks:**
  1. not logged in (401);
  2. unknown event (404);
  3. not the assigned coordinator (403);
  4. not Submitted (409);
  5. the save fails (503).

  The request's row is locked before its status is checked. If two starts happen at once, the second sees Under Review and is refused.
- **A16 — No way back:** a started review can't be undone (moved back to Submitted). *(Q10)*

## Endpoints under test

- `POST /api/events/<id>/clarifications` with body `{"message": str}` → **201** `{"message": str, "clarification": {...}, "notification": {"in_app": true, "email_queued": bool}}`
- `GET /api/events/<id>/clarifications` → **200** `{"event": {"id", "title", "status", "organiser": {"id", "email"}}, "clarifications": [...], "message": str | null}`. The list is oldest first, and `message` holds the empty-state text.
- `GET /api/notifications/` → **200** `{"notifications": [...]}`: the caller's own notifications, newest first.
- A clarification is `{"id", "event_id", "sender": {"id", "email"}, "message", "created_at"}`.
- Errors are `{"error": str}`. A save failure is **503** with `"retryable": true`.
- **Reopened (AC7–AC10):** `POST /api/events/<id>/review` (no body):
  - **200** `{"message", "request"}`, where `request` is SCRUM-32's review payload, which now also has `"review_started_at"` and `"review_started_by": {"id", "email"} | null`.
  - **401**, **404**, **403**.
  - **409** `{"error"}` when the request isn't Submitted.
  - **503** `{"error", "retryable": true}`.

  `GET /api/events/<id>/review` returns the same two new fields.

## Seed data (CL-SEED)

Reset the database to this data before **every** test case. Users and events come from `backend/tests/seed_data.py`.

| Ref | Event | Status | Organiser | Coordinator |
|-----|-------|--------|-----------|-------------|
| E1 | Charity Gala (`assigned`) | submitted | dana | alice |
| E2 | Product Launch (`evans_event`) | submitted | evan | ben |
| E3 | Tech Summit 2026 (`unassigned`) | submitted | dana | *none* |
| E4 | Draft Workshop (`draft`) | draft | dana | *none* |
| E5 | Cancelled Meetup (`cancelled`) | cancelled | dana | *none* |

Other users: chloe (coordinator of nothing), admin, farah (attendee), gus (venue staff), hana (tech staff).

---

## AC1 — Send clarification questions

**TC-31-01 · Assigned coordinator sends a question**
- **Traces to:** AC1, AC3, AC6 · **Type:** Happy path
- **Preconditions:** CL-SEED loaded; logged in as `alice`.
- **Steps:** 1. Open E1's clarification page. 2. Type the question. 3. Click Send.
- **Test data:** Message = "What is the expected attendance, and do any guests need wheelchair access?"
- **Expected result:** HTTP 201. "Your question was sent to dana…" is shown. The question is saved against E1 with alice as sender and the send time. dana receives a notification.

**TC-31-02 · Sent questions are listed for the coordinator and the organiser**
- **Traces to:** AC1, AC3 · **Type:** Happy path
- **Preconditions:** CL-SEED loaded; alice has sent two questions on E1.
- **Steps:** View E1's clarifications as `alice`, then as `dana`.
- **Expected result:** Both see E1's title, status and organiser, and both questions, oldest first, each with sender and time.

**TC-31-03 · Event with no questions yet**
- **Traces to:** AC1 · **Type:** Happy path (empty state)
- **Steps:** As `alice`, view E1's clarifications before sending anything.
- **Expected result:** An empty list and a message saying no questions have been sent yet.

**TC-31-04 · Coordinator not assigned to the event is refused**
- **Traces to:** AC1, AC4 · **Type:** Negative (authorisation) · **Depends on:** Q1
- **Steps:** As `ben` (E2's coordinator) and as `chloe` (no events), send a question on E1. Then as `alice`, send one on E3 (unassigned).
- **Expected result:** HTTP 403 with an error saying only the event's assigned coordinator can send questions. Nothing is saved and nobody is notified.

**TC-31-05 · Other roles are refused**
- **Traces to:** AC1 · **Type:** Negative (authorisation)
- **Steps:** As each of admin, dana (E1's own organiser), farah, gus and hana, send a question on E1.
- **Expected result:** HTTP 403 for each. Nothing is saved and nobody is notified.

**TC-31-06 · Access follows reassignment and role changes**
- **Traces to:** AC1 · **Type:** Boundary (authorisation)
- **Steps:** 1. With alice's token, send a question on E1 (succeeds). 2. Reassign E1 to ben; send again with alice's same token. 3. Change ben's role to organiser; send with ben's earlier token.
- **Expected result:** (2) and (3) are refused with HTTP 403. Only the question from (1) is saved.

**TC-31-07 · Session required**
- **Traces to:** AC1 · **Type:** Negative (authentication)
- **Steps:** Send a question on E1 with no token, with an expired token, and with a token for a user who has since been deleted.
- **Expected result:** HTTP 401 each time. Nothing is saved.

**TC-31-08 · Unknown event**
- **Traces to:** AC1, AC4 · **Type:** Negative
- **Steps:** As `alice`, send a question on an event ID that does not exist.
- **Expected result:** HTTP 404 "Event not found." Nothing is saved.

**TC-31-09 · Event not open for clarification**
- **Traces to:** AC1, AC4 · **Type:** Negative (business rule) · **Depends on:** Q2
- **Preconditions:** alice is made coordinator of E4 (draft) and E5 (cancelled).
- **Steps:** As `alice`, send a question on E4, then on E5.
- **Expected result:** HTTP 409 with an error naming the event's status. Nothing is saved and nobody is notified.

**TC-31-10 · Sending a question does not change the event**
- **Traces to:** AC1 · **Type:** Negative (business rule) · **Depends on:** Q3
- **Steps:** As `alice`, send a question on E1, then reload E1.
- **Expected result:** Every field of E1, including its status "submitted", is unchanged.

**TC-31-11 · Unrelated users cannot view an event's questions**
- **Traces to:** AC1 · **Type:** Negative (authorisation)
- **Preconditions:** alice has sent a question on E1.
- **Steps:** View E1's clarifications as ben, evan, farah and admin.
- **Expected result:** HTTP 403. The question text, title and emails do not appear in the response.

## AC2 — Questions are limited to 1,000 words

**TC-31-12 · Exactly 1,000 words is accepted**
- **Traces to:** AC2 · **Type:** Boundary
- **Test data:** 1,000 words separated by single spaces; and 1,000 words separated by a mix of spaces, tabs and new lines.
- **Expected result:** Both are sent (HTTP 201).

**TC-31-13 · 1,001 words is refused with an explanation**
- **Traces to:** AC2, AC4 · **Type:** Boundary
- **Test data:** 1,001 words.
- **Expected result:** HTTP 400. The error states the 1,000-word limit and that 1,001 words were entered. Nothing is saved and nobody is notified.

**TC-31-14 · Frontend word counter**
- **Traces to:** AC2, AC4 · **Type:** Boundary (frontend)
- **Steps:** Type 1,000 words, then one more.
- **Expected result:** A live counter shows "1000 / 1000 words" and Send is enabled. At 1,001 it shows the limit is exceeded, explains how many words to remove, and Send is disabled.

## AC3 — The coordinator is shown the question was sent

**TC-31-15 · Success is confirmed and the page updates**
- **Traces to:** AC3 · **Type:** Happy path (frontend)
- **Steps:** Send a valid question from E1's clarification page.
- **Expected result:** A confirmation naming the organiser is shown, the text box is cleared, and the new question appears in the list.

## AC4 — Failures are explained and actionable

**TC-31-16 · Save fails: retryable error, nothing half-sent**
- **Traces to:** AC4, AC6 · **Type:** Negative (failure)
- **Preconditions:** The database is made to fail when saving (in automated tests, the commit raises `SQLAlchemyError`).
- **Steps:** As `alice`, send a question on E1.
- **Expected result:** HTTP 503 with `retryable: true` and an error saying the question was not sent and to try again. No question and no notification are saved, and no email is queued.

**TC-31-17 · Retry succeeds after recovery**
- **Traces to:** AC4 · **Type:** Happy path (recovery)
- **Steps:** After TC-31-16, send the same question again with the database working.
- **Expected result:** HTTP 201. Exactly one copy of the question is saved.

**TC-31-18 · Frontend keeps the question and shows why sending failed**
- **Traces to:** AC4 · **Type:** Negative (frontend)
- **Steps:** Send a question when the server returns 400, 403, 409 or 503, and when there is no network.
- **Expected result:** The server's explanation is shown (or, with no response, a message to check the connection and try again). The typed question stays in the box so it can be resent, and Send is enabled again.

## AC5 — Empty messages cannot be sent

**TC-31-19 · Empty messages are refused by the API**
- **Traces to:** AC5, AC4 · **Type:** Negative
- **Test data:** Message missing; `""`; `"   \n\t "`; `null`; a number; a body that is not JSON.
- **Expected result:** HTTP 400 with an error asking for a question. Nothing is saved and nobody is notified.

**TC-31-20 · Surrounding whitespace is trimmed**
- **Traces to:** AC5 · **Type:** Boundary
- **Test data:** `"  Is catering needed?\n"`.
- **Expected result:** Saved as "Is catering needed?".

**TC-31-21 · Frontend blocks empty messages**
- **Traces to:** AC5 · **Type:** Negative (frontend)
- **Steps:** Leave the box empty, or type only spaces.
- **Expected result:** Send is disabled and no request is made.

## AC6 — The organiser is notified

**TC-31-22 · Organiser receives an in-app notification**
- **Traces to:** AC6 · **Type:** Happy path
- **Steps:** As `alice`, send a question on E1. Then list notifications as `dana`, and as `evan` and `alice`.
- **Expected result:** dana has one new unread notification of kind `clarification_requested`, linked to E1, naming the event. evan and alice have no new notification.

**TC-31-23 · Organiser is emailed**
- **Traces to:** AC6 · **Type:** Happy path
- **Steps:** As `alice`, send a question on E1.
- **Expected result:** One email is queued to dana's address, with the event title in the subject and the question in the body. The response has `email_queued: true`.

**TC-31-24 · Email cannot be queued: question still sent**
- **Traces to:** AC3, AC6 · **Type:** Negative (failure) · **Depends on:** Q5
- **Preconditions:** Queuing the email raises an error (e.g. Redis is down).
- **Steps:** As `alice`, send a question on E1.
- **Expected result:** HTTP 201 with `email_queued: false`. The question and dana's in-app notification are saved.

**TC-31-25 · Notifications require a session**
- **Traces to:** AC6 · **Type:** Negative (authentication)
- **Steps:** List notifications with no token.
- **Expected result:** HTTP 401.

## AC7–AC10 — Starting a review (reopened 26 Oct 2026)

**Seed data (RV-SEED):**
- SCRUM-32's DC-SEED:
  - R1 Harbour Lights Festival: submitted, coordinator alice;
  - R2: submitted, ben;
  - R3: submitted, no coordinator;
  - R4: draft;
  - R5: approved;
  - R6: rejected;
  - R7: cancelled;
  - E1 Alumni Mixer: submitted, alice, organised by evan.
- Plus R8 Spring Fair (under review, alice) and lena, a Coordinator Lead.

**TC-31-26 · Another coordinator can't start the review**
- **Traces to:** AC7 · **Type:** Negative (authorisation) · **Depends on:** Q1
- **Steps:** As ben, start the review of R1 (alice's).
- **Expected result:** HTTP 403. R1 is unchanged.
- **Automated:** `test_another_coordinator_cannot_start_the_review`

**TC-31-27 · No other role can start a review**
- **Traces to:** AC7 · **Type:** Negative (authorisation)
- **Steps:** Start R1's review as admin, lena (Lead), dana (its organiser), farah, gus and hana.
- **Expected result:** HTTP 403 each time, and the error doesn't name the request. R1 is unchanged.
- **Automated:** `test_no_other_role_can_start_a_review`

**TC-31-28 · A request with no coordinator can't be started**
- **Traces to:** AC7 · **Type:** Negative · **Depends on:** Q1
- **Steps:** As alice, start R3's review.
- **Expected result:** HTTP 403. R3 is unchanged.
- **Automated:** `test_request_without_a_coordinator_cannot_be_started`

**TC-31-29 · A valid session is required**
- **Traces to:** AC7 · **Type:** Negative (authentication)
- **Steps:** Use no token, an expired token, and a token for a deleted user.
- **Expected result:** HTTP 401. R1 is unchanged.
- **Automated:** `test_a_valid_session_is_required`

**TC-31-30 · Unknown event**
- **Traces to:** AC7 · **Type:** Negative
- **Expected result:** HTTP 404.
- **Automated:** `test_unknown_event_is_not_found`

**TC-31-31 · The assigned coordinator starts reviewing a submitted request**
- **Traces to:** AC8 · **Type:** Happy path
- **Steps:** As alice, start R1's review.
- **Expected result:**
  - HTTP 200.
  - R1 is `under_review`, started by alice, at a time between the request's start and end (naive UTC).
  - The reply's request shows the same status, time and person. Its message names the request.
  - Nothing else about R1 changes.
- **Automated:** `test_assigned_coordinator_starts_the_review`

**TC-31-32 · The new status shows wherever the request is listed**
- **Traces to:** AC8 · **Type:** Happy path
- **Steps:** After TC-31-31, load:
  - R1's review page;
  - alice's requests for review;
  - dana's "My requests" and "My event requests".
- **Expected result:** each shows R1 as `under_review`. The review page also shows who started the review and when.
- **Automated:** `test_status_shows_wherever_the_request_is_listed`

**TC-31-33 · Starting a review notifies nobody**
- **Traces to:** AC8 · **Type:** Negative · **Depends on:** Q9
- **Expected result:** After TC-31-31, nobody has a new notification and no email was queued.
- **Automated:** `test_starting_a_review_notifies_nobody`

**TC-31-34 · Once the review has started, the coordinator can still ask questions and decide**
- **Traces to:** AC8 · **Type:** Happy path · **Depends on:** Q7, Q8
- **Steps:**
  1. Start R1's review, then send a question and approve it.
  2. Start E1's review, then reject it with a reason.
- **Expected result:**
  - The question is sent (201).
  - R1 becomes approved and E1 rejected (HTTP 200), each with its decision recorded.
- **Automated:** `test_coordinator_can_ask_and_decide_once_the_review_has_started`

**TC-31-35 · A request that is not Submitted can't be started**
- **Traces to:** AC9 · **Type:** Negative (business rule)
- **Steps:** As alice, start the review of R4 (draft), R5 (approved), R6 (rejected), R7 (cancelled) and R8 (under review).
- **Expected result:** HTTP 409 each time, naming the status. Nothing changes.
- **Automated:** `test_request_that_is_not_submitted_cannot_be_started`

**TC-31-36 · Starting twice keeps the first start**
- **Traces to:** AC9 · **Type:** Negative
- **Steps:** Start R1's review twice.
- **Expected result:** The second call gives HTTP 409, naming `under_review`. Who and when are still from the first.
- **Automated:** `test_starting_twice_keeps_the_first_start`

**TC-31-37 · Two starts at once are handled one at a time**
- **Traces to:** AC9 · **Type:** Concurrency
- **Expected result:** The request's row is locked (`SELECT … FOR UPDATE`) before its status is read.
- **Automated:** `test_request_row_is_locked_before_its_status_is_checked`

**TC-31-38 · Saving fails: the status is unchanged and an error is shown**
- **Traces to:** AC10 · **Type:** Negative (failure)
- **Preconditions:** The commit raises `SQLAlchemyError`.
- **Expected result:**
  - HTTP 503 with `retryable: true`, saying the review was not started and to try again.
  - R1 is still submitted, with no start recorded.
  - Retrying with the database working succeeds.
- **Automated:** `test_failed_save_leaves_the_request_submitted`

**TC-31-39 · A failed decision on a request under review doesn't claim it is "still submitted"**
- **Traces to:** AC10 · **Type:** Negative (failure) · **Depends on:** Q7
- **Preconditions:** R8 is under review. The commit raises `SQLAlchemyError` when alice approves it.
- **Expected result:** HTTP 503. The error says the decision was not saved and doesn't say "submitted". R8 is still under review.
- **Automated:** `test_failed_decision_does_not_claim_the_request_is_submitted`

**TC-31-40 · Frontend: start the review from the review page**
- **Traces to:** AC8 · **Type:** Happy path (frontend)
- **Steps:** Open a submitted request and press "Start review".
- **Expected result:**
  - The request is sent to `POST /events/<id>/review`.
  - The page shows "Status: Under review", the server's confirmation, and "Review started by … on …".
  - "Start review" is gone, and Approve and Reject are still offered.
- **Automated:** "starts the review and keeps the decision available" (`ReviewRequestPage.test.jsx`)

**TC-31-41 · Frontend: a refused or failed start is explained**
- **Traces to:** AC7, AC9, AC10 · **Type:** Negative (frontend)
- **Steps:** The server refuses with 403, 409 or 503, or the network fails.
- **Expected result:** The server's message, or a fallback asking to check the connection, is shown. The status stays Submitted, and "Start review" is still offered.
- **Automated:** "explains why the review could not be started" (`ReviewRequestPage.test.jsx`)

**TC-31-42 · Frontend: a request already under review**
- **Traces to:** AC8, AC9 · **Type:** Happy path (frontend) · **Depends on:** Q7
- **Expected result:** It shows who started the review and when. There's no "Start review", and Approve and Reject are offered. This replaces SCRUM-77's TC-77-07 for Under Review.
- **Automated:** "shows who started the review and offers the decision" (`ReviewRequestPage.test.jsx`)

**Changed in other stories' tests** (Week 7 *Guide to Managing Changes*):
- **SCRUM-77 and SCRUM-78:** TC-77-01/02 and TC-78-01/02 now expect a request under review to be approved or rejected. TC-77-07 no longer lists Under Review among the statuses without buttons.
- **SCRUM-53:** TC-53-20 adds `review_started_at` and `review_started_by_id` to the fields the normal edit refuses. This passes before the change too; it is there to fail if the fields ever become editable.

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11 |
| AC2 | 12, 13, 14 |
| AC3 | 01, 02, 15, 24 |
| AC4 | 04, 08, 09, 13, 14, 16, 17, 18, 19 |
| AC5 | 19, 20, 21 |
| AC6 | 01, 16, 22, 23, 24, 25 |
| AC7 | 26, 27, 28, 29, 30, 41 |
| AC8 | 31, 32, 33, 34, 40, 42 |
| AC9 | 35, 36, 37, 41, 42 |
| AC10 | 38, 39, 41 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 02, 03, 15, 17, 22, 23, 31, 32, 34, 40, 42 |
| Negative | 04, 05, 07, 08, 09, 10, 11, 16, 18, 19, 21, 24, 25, 26, 27, 28, 29, 30, 33, 35, 36, 38, 39, 41 |
| Boundary | 06, 12, 13, 14, 20 |
| Concurrency | 37 |
| Cross-cutting (authorisation) | 04, 05, 06, 07, 11, 25, 26, 27, 28, 29 |
| Frontend | 14, 15, 18, 21, 40, 41, 42 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Who may ask the organiser for clarification: only the event's assigned coordinator (assumed), or any coordinator reviewing unassigned requests? | A1, TC-31-04, 06 |
| Q2 | At which stages can clarification be requested? Only while submitted / under review (assumed), or also after approval? | A2, TC-31-09 |
| Q3 | Should sending a question move the event to a status such as "awaiting clarification"? | A3, TC-31-10 |
| Q4 | Is the limit 1,000 words (assumed) or 1,000 characters? | A4, TC-31-12–14 |
| Q5 | If the email cannot be sent, is the in-app notification enough, or must sending fail? | A6, TC-31-24 |
| Q6 | The story's first two criteria read the same. Is one of them meant to be something else, e.g. the organiser replying? | AC1 |
| Q7 | Can a request that is Under Review be approved or rejected? The team decided yes (26 Oct 2026), since otherwise starting a review blocks the decision, but SCRUM-77/78's criteria say "Submitted" only. | A13, TC-31-34, 39, 42 |
| Q8 | Should sending the first question start the review automatically? Assumed not: starting is its own action. | A14 |
| Q9 | Should the organiser be told when the review starts? Assumed not: they see the status in their lists. | A12, TC-31-33 |
| Q10 | Can a started review be stopped, returning the request to Submitted? Assumed not. | A16 |
