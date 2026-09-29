# SCRUM-32 — Approve or Reject an Event Request: Test Cases

**User story:** As an Event Coordinator, I want to approve or reject a submitted event request so that only feasible events proceed to further planning.

**Created:** 28 Sep 2026 · **Status of all cases:** Automated cases pass (28 Sep 2026, local PostgreSQL with db/event_decisions.sql applied + Vitest); frontend cases 20 and 21 also to be checked manually in the browser · **Automated tests:** `backend/tests/test_event_decisions.py`, `frontend/src/pages/ReviewRequestPage.test.jsx`, `frontend/src/pages/MyRequestsPage.test.jsx`

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | Only event requests with status Submitted can be approved or rejected by the Event Coordinator. |
| AC2 | If the coordinator approves, the request's status is updated to Approved. |
| AC3 | The coordinator must provide a reason for rejecting. |
| AC4 | If the coordinator rejects, the request's status is updated to Rejected and the reason is recorded. |
| AC5 | The Event Organiser receives a notification of the outcome. |
| AC6 | The Event Organiser can view the outcome, and the reason if rejected. |

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — Who decides:** only the request's assigned coordinator (`Event.coordinator_id`, SCRUM-33), and only while their role is still `coordinator`. This is checked against the database on every request. An unassigned request must be assigned first. *(Q1)*
- **A2 — Which requests:** only status `submitted`. Drafts, and requests that are already approved, rejected or cancelled, are refused, so a decision cannot be changed or repeated through this story. *(Q2)*
- **A3 — Reason:** rejecting needs a reason that is not empty or only whitespace, of at most 1,000 words (a word is a run of characters between whitespace, as in SCRUM-31). Approving may include an optional note under the same limit. Text is trimmed before saving. *(Q3)*
- **A4 — Recorded with the decision:** the new status, the reason or note, when it was decided (naive UTC), and who decided.
- **A5 — Notification:** the organiser gets an in-app notification (kind `request_approved` or `request_rejected`), saved in the same commit as the decision: both are saved, or neither is. An email is then queued through the Celery task. If the email cannot be queued, the decision still stands and the response says the email was not queued (as in SCRUM-31).
- **A6 — Organiser's view:** the organiser's "my event requests" list shows each of their submitted, approved and rejected requests with its status, the decision time, and the reason (if rejected) or note (if approved). Drafts stay on the SCRUM-29 drafts list.
- **A7 — Coordinator's review view:** the assigned coordinator can open the full request (every SCRUM-29 field) and its decision details, in any status.
- **A8 — Order of checks:** not logged in (401), unknown request (404), not allowed (403), invalid decision or reason (400), not submitted (409).

## Endpoints under test

- `GET /api/events/<id>/review` → **200** `{"request": request}`. The full request, for the assigned coordinator.
- `POST /api/events/<id>/decision` with body `{"decision": "approve" | "reject", "reason": str}` → **200** `{"message": str, "request": request, "notification": {"in_app": true, "email_queued": bool}}`.
- `GET /api/events/requests` → **200** `{"requests": [summary, ...], "message": str | null}`. The caller's own non-draft requests, most recently submitted first. `message` holds the empty-state text.
- A request is every SCRUM-29 field plus `"id"`, `"status"`, `"submitted_at"`, `"decided_at"`, `"decided_by": {"id", "email"} | null` and `"decision_note"`.
- A summary is `{"id", "title", "status", "submitted_at", "decided_at", "decision_note"}`.
- Errors are `{"error": str}`. A save failure is **503** with `"retryable": true`.

## Seed data (DC-SEED)

Reset the database to this data before **every** test case. Users come from `backend/tests/seed_data.py`: alice, ben, chloe (coordinators), dana, evan (organisers), admin, farah, gus, hana.

| Ref | Title | Organiser | Coordinator | Status | Notes |
|-----|-------|-----------|-------------|--------|-------|
| R1 | Harbour Lights Festival | dana | alice | submitted | every SCRUM-29 field; submitted 20 Sep 2026 |
| R2 | Winter Networking Night | dana | ben | submitted | submitted 22 Sep 2026 |
| R3 | Spring Garden Party | dana | *none* | submitted | |
| R4 | Tech Summit Draft | dana | alice | draft | |
| R5 | Product Launch | dana | alice | approved | note "Venue confirmed"; decided 10 Sep 2026 |
| R6 | Rooftop Cinema | dana | alice | rejected | reason "No licensed venue is available"; decided 12 Sep 2026 |
| R7 | Cancelled Meetup | dana | alice | cancelled | |
| E1 | Alumni Mixer | evan | alice | submitted | |

---

## AC1 — Only submitted requests can be decided

**TC-32-01 · Requests that are not submitted cannot be decided**
- **Traces to:** AC1 · **Type:** Negative (business rule) · **Depends on:** Q2
- **Steps:** As `alice`, approve and then reject (with a reason) each of R4 (draft), R5 (approved), R6 (rejected) and R7 (cancelled).
- **Expected result:** HTTP 409 naming the current status. Each request is unchanged, and nobody is notified.

**TC-32-02 · Only the assigned coordinator can decide**
- **Traces to:** AC1 · **Type:** Negative (authorisation) · **Depends on:** Q1
- **Steps:** Approve R1 as ben, chloe, admin, dana (its organiser), farah, gus and hana. Then, as `alice`, approve R2 (ben's) and R3 (unassigned).
- **Expected result:** HTTP 403 each time. Nothing changes and nobody is notified.

**TC-32-03 · Access follows reassignment and role changes**
- **Traces to:** AC1 · **Type:** Boundary (authorisation)
- **Steps:** 1. Reassign R1 to ben, then approve it with alice's earlier token. 2. Change ben's role to organiser, then approve with ben's earlier token.
- **Expected result:** Both are refused with HTTP 403, and R1 stays submitted.

**TC-32-04 · A valid session is required, and the request must exist**
- **Traces to:** AC1 · **Type:** Negative
- **Steps:** Decide, and open the review view, with no token, an expired token and a deleted user's token. Then decide a request ID that does not exist.
- **Expected result:** HTTP 401, then HTTP 404. Nothing changes.

**TC-32-05 · The decision must be approve or reject**
- **Traces to:** AC1 · **Type:** Negative
- **Test data:** decision missing, `"maybe"`, `"APPROVE "` (not an exact value), `1`; a body that is not JSON.
- **Expected result:** HTTP 400. R1 stays submitted.

**TC-32-06 · Coordinator opens the full request to review it**
- **Traces to:** AC1, AC6 · **Type:** Happy path
- **Steps:** As `alice`, open R1's review view. Then open it as ben and as dana.
- **Expected result:** alice sees every SCRUM-29 field, status "submitted", and no decision yet. ben and dana get HTTP 403.

## AC2 — Approving

**TC-32-07 · Approving updates the status to Approved**
- **Traces to:** AC2, AC5 · **Type:** Happy path
- **Steps:** As `alice`, approve R1 without a note.
- **Expected result:** HTTP 200. R1's status is "approved", with the decision time (between just before and just after the request), alice as decider, and no note. The confirmation names the organiser. Every SCRUM-29 field is unchanged.

**TC-32-08 · Approving with an optional note**
- **Traces to:** AC2, AC6 · **Type:** Happy path
- **Test data:** Reason = `"  Please book the venue by 1 Nov. "`.
- **Expected result:** Approved, with the note saved as "Please book the venue by 1 Nov.".

**TC-32-09 · A decided request cannot be decided again**
- **Traces to:** AC1, AC2 · **Type:** Negative
- **Steps:** Approve R1, then approve it again, then reject it.
- **Expected result:** The second and third calls give HTTP 409. R1 stays approved with its first decision time. Only one notification is sent.

## AC3 — A reason is required to reject

**TC-32-10 · Rejecting without a reason is refused**
- **Traces to:** AC3 · **Type:** Negative
- **Test data:** Reason missing, `""`, `"  \n\t "`, `null`, `42`.
- **Expected result:** HTTP 400 asking for a reason. R1 stays submitted, and nobody is notified.

**TC-32-11 · Reason length limits**
- **Traces to:** AC3 · **Type:** Boundary · **Depends on:** Q3
- **Test data:** A 1,000-word reason; a 1,001-word reason; a 1,001-word approval note.
- **Expected result:** 1,000 words is accepted. 1,001 words is refused with HTTP 400 stating the limit and the count, for both reasons and notes.

## AC4 — Rejecting

**TC-32-12 · Rejecting updates the status and records the reason**
- **Traces to:** AC4, AC5 · **Type:** Happy path
- **Steps:** As `alice`, reject R1 with reason "The proposed date clashes with the National Day Parade."
- **Expected result:** HTTP 200. R1's status is "rejected", with the reason, the decision time, and alice as decider. Every SCRUM-29 field is unchanged.

## AC5 — The organiser is notified

**TC-32-13 · In-app notification of the outcome**
- **Traces to:** AC5 · **Type:** Happy path
- **Steps:** Approve R1, then list dana's notifications. Then, with fresh seed data, reject R1 and list them again.
- **Expected result:** dana has exactly one new notification each time: kind `request_approved` or `request_rejected`, linked to R1, naming the event, and for a rejection including the reason. evan and alice get none.

**TC-32-14 · Email of the outcome**
- **Traces to:** AC5 · **Type:** Happy path
- **Expected result:** One email is queued to dana, with the event title and outcome in the subject, and the reason (if rejected) in the body. The response has `email_queued: true`.

**TC-32-15 · Email cannot be queued: the decision still stands**
- **Traces to:** AC5 · **Type:** Negative (failure)
- **Expected result:** HTTP 200 with `email_queued: false`. The decision and the in-app notification are saved.

**TC-32-16 · Save fails: nothing changes, retry works**
- **Traces to:** AC2, AC4, AC5 · **Type:** Negative (failure)
- **Preconditions:** The commit raises `SQLAlchemyError`.
- **Expected result:** HTTP 503 with `retryable: true`, saying the decision was not saved and to try again. R1 stays submitted, no notification is saved and no email is queued. Retrying with the database working succeeds.

## AC6 — The organiser can view the outcome

**TC-32-17 · Organiser's list of event requests**
- **Traces to:** AC6 · **Type:** Happy path
- **Steps:** As `dana`, list event requests.
- **Expected result:** dana sees R1, R2, R3, R5, R6 and R7 (not the draft R4, and not evan's E1), most recently submitted first. R5 shows status "approved" with its note, and R6 shows "rejected" with its reason and decision time. Submitted ones have no decision.

**TC-32-18 · The list reflects a new decision**
- **Traces to:** AC4, AC6 · **Type:** Happy path
- **Steps:** alice rejects R1 with a reason, then dana lists her requests.
- **Expected result:** R1 is shown as "rejected" with that reason and its decision time.

**TC-32-19 · Only organisers have a request list; the empty state**
- **Traces to:** AC6 · **Type:** Negative / empty state
- **Expected result:** An organiser with no requests gets an empty list and a message. Coordinators and attendees get HTTP 403. No token gives HTTP 401.

## Frontend

**TC-32-20 · Coordinator review page**
- **Traces to:** AC1–AC4 · **Type:** Frontend
- **Expected result:** The page shows the request's details and status. For a submitted request, Approve is enabled; Reject is disabled until a reason is typed, and a live word counter blocks more than 1,000 words. After deciding, the new status and reason are shown, the buttons are gone, and a confirmation appears. On failure, the error is shown and the typed reason stays. A request that is not submitted shows its outcome with no buttons.

**TC-32-21 · Organiser's "My event requests" page**
- **Traces to:** AC6 · **Type:** Frontend
- **Expected result:** Each request shows its title, status (Submitted / Approved / Rejected) and, when decided, the decision time. A rejected request shows "Reason: …", and an approved one with a note shows "Note: …". There is an empty state, and a retryable error if loading fails.

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 03, 04, 05, 06, 09, 20 |
| AC2 | 07, 08, 09, 16, 20 |
| AC3 | 10, 11, 20 |
| AC4 | 12, 16, 18, 20 |
| AC5 | 07, 12, 13, 14, 15, 16 |
| AC6 | 06, 08, 17, 18, 19, 21 |

| Type | Test cases |
|------|-----------|
| Happy path | 06, 07, 08, 12, 13, 14, 17, 18 |
| Negative | 01, 02, 04, 05, 09, 10, 15, 16, 19 |
| Boundary | 03, 11 |
| Cross-cutting (authorisation) | 02, 03, 04, 06, 19 |
| Frontend | 20, 21 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | May only the assigned coordinator decide (assumed), or any coordinator? | A1, TC-32-02 |
| Q2 | Can a decision be reversed (e.g. a rejected request resubmitted or re-approved)? Assumed not in this story. | A2, TC-32-01, 09 |
| Q3 | Is 1,000 words the right limit for a reason? Should approval allow a note (assumed) or no text? | A3, TC-32-08, 11 |
| Q4 | Should rejected requests be editable and resubmittable by the organiser? | New story if yes |
| Q5 | Should "under review" requests also be decidable? Assumed not (the AC says Submitted only). | A2 |
