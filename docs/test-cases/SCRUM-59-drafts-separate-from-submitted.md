# SCRUM-59 — See Drafts Separately from Submitted Requests: Test Cases

**User story:** As an Event Organiser, I want to see my draft requests clearly separated from my submitted ones so that I can find and finish the requests I haven't submitted yet.

**Created:** 9 Oct 2026 · **Status of all cases:** Automated tests written first (TDD, red); they fail until the story is implemented. · **Automated tests:** `backend/tests/test_my_event_requests.py`, `frontend/src/pages/MyEventRequestsPage.test.jsx` · **Endpoint:** `GET /api/events/mine` · **Related:** SCRUM-29 (drafts, the draft editor), SCRUM-32 (decisions on submitted requests)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The organiser can view a list of their own event requests. |
| AC2 | Drafts are labelled Draft and show their last-saved date and time; submitted requests show their current status. |
| AC3 | Drafts are visually distinguishable from submitted requests (for example, a separate section or a status label). |
| AC4 | Opening a draft from the list resumes editing with its saved information. |
| AC5 | Submitted requests are not opened as editable drafts. |
| AC6 | A draft saved without an event name is shown as "Untitled draft". |
| AC7 | If the organiser has no requests, an empty-state message is shown. |
| AC8 | If the list cannot be loaded, the organiser is informed and can retry. |

## Working assumptions

These are the team's current reading of the story. Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **A1 — One list, two sections:** a new page, "My event requests", shows **Drafts** and **Submitted requests** as two separately headed sections, loaded together from one endpoint so they never disagree (e.g. a request submitted between two loads appearing in both or neither). The existing SCRUM-29 drafts page and SCRUM-32 requests page are left as they are. *(Q2)*
- **A2 — Whose requests:** only the caller's own requests, and only for users whose role is `organiser`, checked in the database on every request (as in SCRUM-29 and SCRUM-32).
- **A3 — What counts as submitted:** every status other than `draft`: `submitted`, `under_review`, `approved`, `rejected`, `cancelled` and `confirmed`. Each shows its current status label, plus the decision time and the reason or note when there is one (as in SCRUM-32).
- **A4 — Order:** drafts are listed most recently saved first, and submitted requests most recently submitted first, matching the SCRUM-29 and SCRUM-32 lists.
- **A5 — Opening a draft:** each draft links to the SCRUM-29 draft editor (`/events/drafts/<id>`), which loads its saved information. Submitted requests have no link to the editor. If a submitted request's ID is opened in the editor anyway, the API refuses it (SCRUM-29, HTTP 409) and nothing can be saved.
- **A6 — "Untitled draft" is display-only:** SCRUM-29 still requires an event name to save a draft (TC-29-03), and `events.title` cannot be NULL. So a nameless draft can only be one whose stored name is blank (empty or whitespace), for example from older data. The API returns its `title` as `null` and the page shows "Untitled draft". *(Q1)*
- **A7 — Empty state:** if the organiser has no drafts and no submitted requests, `message` holds the empty-state text and the page shows it instead of the two sections. If only one section is empty, that section says so briefly.
- **A8 — Load failure:** HTTP 503 with `retryable: true`. The page shows the message with a Retry button.

## Endpoint under test

- `GET /api/events/mine` → **200** `{"drafts": [draft, ...], "submitted": [request, ...], "message": str | null}`.
  - draft = `{"id", "title", "status", "last_saved_at"}`; `title` is `null` when the stored name is blank.
  - request = `{"id", "title", "status", "submitted_at", "decided_at", "decision_note"}`.
  - `message` is the empty-state text when both lists are empty, otherwise `null`.
- **401** without a valid session; **403** for anyone who is not an organiser; **503** `{"error", "retryable": true}` if loading fails.

## Seed data (ML-SEED)

Users come from `backend/tests/seed_data.py`. Times are naive UTC.

| Ref | Title | Organiser | Status | Saved / submitted | Decision |
|-----|-------|-----------|--------|-------------------|----------|
| D1 | Harbour Lights Festival | dana | draft | last saved 25 Sep 2026 10:00 | — (every field needed to submit, incl. purpose "Celebrate the harbour's reopening", 250 attendees) |
| D2 | Winter Networking Night | dana | draft | last saved 27 Sep 2026 08:30 | — |
| D3 | *(empty)* | dana | draft | last saved 26 Sep 2026 09:00 | — |
| D4 | *(spaces only)* | dana | draft | last saved 24 Sep 2026 09:00 | — |
| S1 | Product Launch | dana | submitted | submitted 20 Sep 2026 09:00 | — |
| S2 | Spring Garden Party | dana | under_review | submitted 21 Sep 2026 09:00 | — |
| S3 | Alumni Mixer | dana | approved | submitted 22 Sep 2026 09:00 | 23 Sep, note "Venue confirmed" |
| S4 | Rooftop Cinema | dana | rejected | submitted 6 Sep 2026 09:00 | 12 Sep, reason "No licensed venue is available" |
| S5 | Cancelled Meetup | dana | cancelled | submitted 1 Sep 2026 09:00 | — |
| E1 | Evan's Draft | evan | draft | last saved 28 Sep 2026 09:00 | — |
| E2 | Evan's Launch | evan | submitted | submitted 23 Sep 2026 09:00 | — |

---

## AC1 — The organiser's own requests

**TC-59-01 · The organiser sees their own requests in two groups**
- **Traces to:** AC1, AC3 · **Type:** Happy path
- **Steps:** As dana, load the list.
- **Expected result:** HTTP 200. `drafts` holds D1–D4 and `submitted` holds S1–S5; evan's E1 and E2 appear in neither. `message` is `null`.

**TC-59-02 · Only organisers, with a valid session**
- **Traces to:** AC1 · **Type:** Negative (authorisation)
- **Steps:** Load the list as admin, alice, farah, gus and hana; then with no token, an expired token and a deleted user's token; then as dana after her role is changed to attendee (using her earlier token).
- **Expected result:** HTTP 403 for the other roles and for dana after the role change; HTTP 401 for the session cases. No request details are returned.

## AC2 — Labels, saved times and statuses

**TC-59-03 · Drafts show Draft and their last-saved time, newest first**
- **Traces to:** AC2 · **Type:** Happy path
- **Expected result:** Drafts are listed D2, D3, D1, D4. Each has status `draft` and its last-saved time, e.g. D1 is `{"id", "title": "Harbour Lights Festival", "status": "draft", "last_saved_at": "2026-09-25T10:00:00"}`.

**TC-59-04 · Submitted requests show their current status, newest first**
- **Traces to:** AC2 · **Type:** Happy path
- **Expected result:** Submitted requests are listed S3, S2, S1, S4, S5, each with its own status. S3 shows its decision time and note; S4 its decision time and reason; S1 has no decision.

## AC3 — Drafts are kept apart from submitted requests

**TC-59-05 · Submitting a draft moves it to the submitted group**
- **Traces to:** AC3 · **Type:** Happy path
- **Steps:** Submit D1, which has every field SCRUM-29 requires, then load the list.
- **Expected result:** D1 is no longer in `drafts` and is first in `submitted`, with status `submitted`. No request appears in both groups.

## AC4 — Opening a draft resumes editing

**TC-59-06 · A listed draft opens with its saved information**
- **Traces to:** AC4 · **Type:** Happy path
- **Steps:** Take D1's ID from the list and open it through the SCRUM-29 draft endpoint.
- **Expected result:** HTTP 200 with status `draft` and its saved purpose and expected attendance.

## AC5 — Submitted requests are not editable drafts

**TC-59-07 · A submitted request cannot be opened or saved as a draft**
- **Traces to:** AC5 · **Type:** Negative
- **Steps:** Take S1's ID from the list. Open it, then try to save a new title, through the SCRUM-29 draft endpoints.
- **Expected result:** HTTP 409 both times. S1's title and status are unchanged.

## AC6 — Untitled drafts

**TC-59-08 · A draft with a blank name is listed with no title**
- **Traces to:** AC6 · **Type:** Boundary · **Depends on:** Q1
- **Expected result:** D3 (empty name) and D4 (spaces only) are listed among the drafts with `title: null`; they are not left out.

## AC7 — Empty state

**TC-59-09 · No requests at all, or only one kind**
- **Traces to:** AC7 · **Type:** Empty state
- **Steps:** Load the list as a new organiser with no requests; then as one with only a draft; then as one with only a submitted request.
- **Expected result:** The first gets two empty lists and a non-empty `message`. The others get `message: null` and one item in the right group.

## AC8 — Loading fails

**TC-59-10 · Loading fails: the organiser is told and can retry**
- **Traces to:** AC8 · **Type:** Negative (failure)
- **Preconditions:** Every database query raises `SQLAlchemyError`.
- **Expected result:** HTTP 503 with `retryable: true` and a message saying the requests could not be loaded and to try again. Loading again with the database working succeeds.

## Frontend

**TC-59-11 · Two labelled sections**
- **Traces to:** AC1, AC2, AC3 · **Type:** Frontend
- **Expected result:** The page "My event requests" has a "Drafts" section and a "Submitted requests" section. Each draft shows its name and "Draft · last saved <local date and time>"; each submitted request shows its name and "Status: <label>", plus the decision time and the reason or note when there is one. No draft appears in the submitted section, or the other way round.

**TC-59-12 · Drafts open in the editor; submitted requests do not**
- **Traces to:** AC4, AC5 · **Type:** Frontend
- **Expected result:** Each draft's name links to `/events/drafts/<id>`. Submitted requests have no link to the draft editor.

**TC-59-13 · Untitled drafts**
- **Traces to:** AC6 · **Type:** Frontend
- **Expected result:** A draft whose title is `null`, empty or only spaces is shown as "Untitled draft", still linked to its editor.

**TC-59-14 · Empty states**
- **Traces to:** AC7 · **Type:** Frontend
- **Expected result:** With no requests, the server's message is shown and neither section is. With only drafts, the submitted section says there are none, and the other way round. The "New event request" link is always there.

**TC-59-15 · Load failure and retry**
- **Traces to:** AC8 · **Type:** Frontend
- **Expected result:** The server's error (or a fallback for a network failure) is shown as an alert with a Retry button; retrying loads the list.

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01, 02, 11 |
| AC2 | 03, 04, 11 |
| AC3 | 01, 05, 11 |
| AC4 | 06, 12 |
| AC5 | 07, 12 |
| AC6 | 08, 13 |
| AC7 | 09, 14 |
| AC8 | 10, 15 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 03, 04, 05, 06 |
| Negative | 02, 07, 10 |
| Boundary | 08 |
| Empty state | 09 |
| Cross-cutting (authorisation) | 02 |
| Frontend | 11, 12, 13, 14, 15 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Should a draft be savable without an event name? SCRUM-29 currently requires one, so "Untitled draft" only covers blank names already in the data. Allowing it would change SCRUM-29 (TC-29-03) and the `events.title` column. | A6, TC-59-08, 13 |
| Q2 | Should this page replace the separate "My drafts" (SCRUM-29) and "My requests" (SCRUM-32) pages? Assumed they stay until the team agrees. | A1 |
| Q3 | Should organisers be able to open a submitted request read-only (to see everything they sent)? Assumed out of scope: submitted requests have no link. | A5 |
