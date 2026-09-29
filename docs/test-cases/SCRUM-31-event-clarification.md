# SCRUM-31 — Review and Request Clarification on an Event Request: Test Cases

**User story:** As an Event Coordinator, I want to review and send clarification questions to an Event Organiser about their submitted event request so that I can obtain the information needed to continue planning the event.

**Created:** 28 Sep 2026 · **Status of all cases:** Automated cases pass (28 Sep 2026, local PostgreSQL + Vitest); TC-31-14, 15, 18, 21 also to be checked manually in the browser · **Automated tests:** `backend/tests/test_event_clarifications.py`, `frontend/src/pages/ClarificationPage.test.jsx`

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The coordinator can send clarification questions (replies) to the organiser of a submitted event request. |
| AC2 | A question is limited to 1,000 words. |
| AC3 | The coordinator is shown that the question was sent successfully. |
| AC4 | If the question could not be sent, the coordinator is shown why, with an actionable error. |
| AC5 | An empty clarification message cannot be sent. |
| AC6 | The Event Organiser is notified when a clarification question is sent. |

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

## Endpoints under test

- `POST /api/events/<id>/clarifications` with body `{"message": str}` → **201** `{"message": str, "clarification": {...}, "notification": {"in_app": true, "email_queued": bool}}`
- `GET /api/events/<id>/clarifications` → **200** `{"event": {"id", "title", "status", "organiser": {"id", "email"}}, "clarifications": [...], "message": str | null}`. The list is oldest first, and `message` holds the empty-state text.
- `GET /api/notifications/` → **200** `{"notifications": [...]}`: the caller's own notifications, newest first.
- A clarification is `{"id", "event_id", "sender": {"id", "email"}, "message", "created_at"}`.
- Errors are `{"error": str}`. A save failure is **503** with `"retryable": true`.

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

| Type | Test cases |
|------|-----------|
| Happy path | 01, 02, 03, 15, 17, 22, 23 |
| Negative | 04, 05, 07, 08, 09, 10, 11, 16, 18, 19, 21, 24, 25 |
| Boundary | 06, 12, 13, 14, 20 |
| Cross-cutting (authorisation) | 04, 05, 06, 07, 11, 25 |
| Frontend | 14, 15, 18, 21 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Who may ask the organiser for clarification: only the event's assigned coordinator (assumed), or any coordinator reviewing unassigned requests? | A1, TC-31-04, 06 |
| Q2 | At which stages can clarification be requested? Only while submitted / under review (assumed), or also after approval? | A2, TC-31-09 |
| Q3 | Should sending a question move the event to a status such as "awaiting clarification"? | A3, TC-31-10 |
| Q4 | Is the limit 1,000 words (assumed) or 1,000 characters? | A4, TC-31-12–14 |
| Q5 | If the email cannot be sent, is the in-app notification enough, or must sending fail? | A6, TC-31-24 |
| Q6 | The story's first two criteria read the same. Is one of them meant to be something else, e.g. the organiser replying? | AC1 |
