# SCRUM-70 — Review Change Request to a Submitted Event: Definition of Done Evidence

**Story:** As an Event Coordinator, I want to review a change request on an event I coordinate and accept or reject it so that changes are approved only after I understand what they affect.

**Branch:** `feature/SCRUM-70-review-change-request` (from `main` at `5a9bb4e`) · **Checked:** 28 Oct 2026 · **Test cases:** [SCRUM-70-review-change-request.md](../test-cases/SCRUM-70-review-change-request.md) · **Screenshots, scripts and raw results:** [SCRUM-70/](SCRUM-70/)

| # | Definition of Done item | Result |
|---|---|---|
| 1 | Acceptance criteria satisfied | ✅ All 9 ACs met, each shown by automated tests and in the running app ([§1](#1-acceptance-criteria-satisfied)) |
| 2 | All test cases pass | ✅ SCRUM-70 backend 43/43 and frontend 14/14; whole backend suite 1104 run, all pass (4 skipped, not SCRUM-70's); whole frontend suite 508/508; end-to-end 8/8 ([§2](#2-all-test-cases-pass)) |
| 3 | Test cases are correct and the code does what it says | ✅ Written test-first (red, then green); 41/41 deliberate breakages caught; behaviour confirmed in a real browser ([§3](#3-test-cases-are-correct-and-the-code-does-what-it-says)) |
| 4 | Evidence of checks documented | ✅ This document, 7 screenshots, the scripts that produced them and the raw results ([§4](#4-evidence-documented)) |

> **Supabase:** `backend/db/event_change_request_decisions.sql`, which adds three columns to `event_change_requests`, was run in the Supabase SQL editor on 28 Oct 2026 (no new table, so `test_role.sql` was not re-run). Afterwards `python -m unittest tests.test_app_factory tests.test_change_request_review tests.test_change_request_review_unit tests.test_change_requests` against Supabase passed 73/73, including `test_database_tables_match_the_models`. The other results below come from a local PostgreSQL 17 built by `ci/build_test_database.py`, as CI's `unittest` job builds it, with the tests logged in as the restricted `connectsphere_test` role.

## What this story changed

- **Database:** `event_change_requests` gains `decided_at`, `decided_by_id` and `decision_reason` (`backend/db/event_change_request_decisions.sql`). A request's status becomes `accepted` or `rejected`.
- **Backend:**
  - `GET /api/events/change-requests`: the coordinator's pending change requests, oldest first.
  - `GET /api/events/<id>/change-requests/<request id>`: the request, what it would affect (venue bookings, equipment, registrations, each with why) and whether it can be decided now.
  - `POST /api/events/<id>/change-requests/<request id>/decision`: accept, or reject with a reason. The event and the request are locked; the decision, the event's new values and the notifications are saved in one commit; emails are queued afterwards, stopping at the first that can't be queued.
  - The rules (what a change affects, what a decision needs, the values to apply) in `backend/app/events/change_review.py`, free of Flask and the database like SCRUM-46's `change_requests.py`.
  - SCRUM-46's form now returns the organiser's `latest_decision`, and its no-coordinator message says the event is waiting for a coordinator (AC5).
- **Frontend:** "Change requests to review" (`/events/change-requests`, in the navigation) and the review page (`/events/:id/change-requests/:requestId`); the organiser's change request page shows the last decision.
- **Docs:** the test-case document; SCRUM-46's test case TC-46-12 and its end-to-end script now expect the new no-coordinator message; AGENTS.md mentions the review endpoints.

## 1. Acceptance criteria satisfied

| AC | Criterion | How it is met | Automated tests | Seen in the running app |
|----|-----------|---------------|-----------------|-------------------------|
| AC1 | I can request a change only for my own events, and only when the event status is Approved. Events that are draft, submitted, under review, rejected or cancelled cannot have a change request. | Submitting is unchanged from SCRUM-46 (organiser, approved only; TC-46-02, 03). Reviewing and deciding are for the event's current coordinator only; others get 403 without the request's details. A request on an event that is no longer approved can't be decided (409 `not_approved`). The coordinator's list shows only their own events' pending requests. | TC-70-01 to 04, 30, 31 | E2E-01, 02 · [01](SCRUM-70/01-review-impact.png) |
| AC2 | For a significant change, I can see which venue bookings, equipment arrangements and registrations it affects before deciding. | Every requested field is significant (A2). New times: every live venue booking, reserved equipment (released on acceptance), the registered attendees who will be told, and registration closing after the new start. New attendance: venues too small; registrations above it. New venue requirements: live bookings. New equipment requirements: recorded equipment requirements. Each item says why; "nothing affected" says so; a failed read is an error. Shown only while the request is pending. | TC-70-01, 05 to 09, 12, 23, 26; `ImpactRuleTests` | E2E-01 · [01](SCRUM-70/01-review-impact.png) |
| AC3 | I can accept or reject a pending request. The decision and the decision time are saved, and the organiser can see the outcome. | `accepted` / `rejected` with `decided_at` and `decided_by`; a decided request can't be decided again (409 `decided`). The organiser's change request page shows the last decision. | TC-70-04, 10 to 14, 27, 30, 32 | E2E-03, 07 · [02](SCRUM-70/02-accepted.png), [06](SCRUM-70/06-organiser-sees-rejection.png) |
| AC4 | Rejecting a request requires a reason (not blank, at most 500 characters) that the organiser can see. | Required to reject; must contain a visible character; at most 500 characters after trimming, with a live counter on the page. Saved trimmed and shown to the organiser in the app and the notification. | TC-70-11, 13, 15, 19, 28, 32; `DecisionRuleTests` | E2E-05, 07 · [04](SCRUM-70/04-reason-too-long.png), [06](SCRUM-70/06-organiser-sees-rejection.png) |
| AC5 | If the event has no assigned coordinator, submission is blocked and I am told the event is waiting for a coordinator. | SCRUM-46's 409 `no_coordinator` now says "This event is waiting for a coordinator to be assigned…". | TC-70-16, TC-46-12 | E2E-08 · [07](SCRUM-70/07-waiting-for-coordinator.png) |
| AC6 | If saving the decision fails, the request and event state are unchanged and an error message is shown. | One commit for everything; any failure is 503, "The decision was not saved, so the change request and the event are unchanged. Please try again.", nothing saved, no email. The event and request are locked before deciding. The page keeps the reason for a retry. | TC-70-09, 17, 18, 29 | E2E-06 · [05](SCRUM-70/05-save-failed.png) |
| AC7 | The organiser is notified of the decision. | In-app `change_request_accepted` / `change_request_rejected` naming the event, outcome, decider, time and the changes or reason, then an email. If the email can't be queued the decision stands (`email_queued: false`). | TC-70-19, 20 | E2E-07 |
| AC8 | Accepting a request applies the proposed values to the event, and the event shows the new values. | The proposed values replace the event's, in the decision's commit; nothing else changes. New times release reserved equipment (SCRUM-44); venue bookings are left for the coordinator (Q3). | TC-70-21 to 23, 27 | E2E-03 · [03](SCRUM-70/03-planning-new-times.png) |
| AC9 | When an accepted change alters the date, time or venue, every registered attendee is notified of the new details. Unregistered attendees are not notified. | Accepted new times: each `registered` attendee gets `event_details_changed` with the new start, end and venue, then an email. Withdrawn or cancelled registrations, other events' attendees, rejections and changes that leave the times alone notify nobody. (The venue can't be changed by a change request; Q2.) | TC-70-24, 25 | E2E-04 |

**Working assumptions.** Each is tied to an open question in the test-case document; none has been agreed with the customer:

- **Q1:** AC1 repeats SCRUM-46's rule for submitting; built as: unchanged, and a coordinator decides only on approved events they coordinate.
- **Q2:** a change request can't change the venue (SCRUM-46), so no accepted request changes it.
- **Q3:** accepted new times leave venue bookings for the coordinator to rebook; they are listed as affected.
- **Q4:** registration closing after a new start is listed as affected, not refused or fixed automatically.
- **Q5:** a request on an event that is no longer approved stays pending.
- **Q6:** the whole request is accepted or rejected.
- **Q7:** attendees are told only of new dates and times.

## 2. All test cases pass

| Suite | Command | Result |
|-------|---------|--------|
| Backend, SCRUM-70 through the API | `python -m unittest tests.test_change_request_review` (from `backend/`) | **25/25 pass** (TC-70-01 to 25) |
| Backend, SCRUM-70 rules (no database) | `python -m unittest tests.test_change_request_review_unit` | **18/18 pass** |
| Backend, SCRUM-46 (the message changed for AC5) | `python -m unittest tests.test_change_requests` | **23/23 pass** |
| Backend, whole suite | `python -m unittest discover` | **Ran 1104 tests: OK, 4 skipped.** The skips are SCRUM-36/37 tests waiting on customer answers and a SCRUM-91 test blocked by SCRUM-93. Includes SCRUM-46's, SCRUM-85's and SCRUM-94's tests. |
| Frontend, SCRUM-70 | `npx vitest run src/pages/ChangeRequestReviewPage.test.jsx src/pages/ChangeRequestsToReviewPage.test.jsx src/pages/ChangeRequestPage.test.jsx` | **14/14 SCRUM-70 tests pass** (review page 8, list 4, organiser's outcome 2, plus SCRUM-46's 10 in the same file; 24/24 in the three files) |
| Frontend, whole suite | `npm test` (from `frontend/`) | **508/508 pass** |
| End-to-end in a real browser | [scripts/e2e_check.mjs](SCRUM-70/scripts/e2e_check.mjs) | **8/8 pass** (§3c), [raw result](SCRUM-70/e2e-results.txt) |

## 3. Test cases are correct and the code does what it says

### a. The test cases match the acceptance criteria

Every AC has at least one API test and, where the user sees it, a page test (traceability matrix in the test-case document). The tests were written first and committed failing (`dae9123`, "TDD, red"): the API tests failed on the missing endpoints (404) and columns, the rules tests on the missing module, the page tests on missing pages, and TC-46-12 on the old message.

Two changes were made to the tests while making them pass, both recorded in the green commit or below:

- **TC-70-02** expected our `error` body on a request with no token at all, but flask-jwt-extended answers that one itself (with `msg`). It now checks only the 401, as SCRUM-46's tests do.
- **The impact after deciding.** The first browser run showed the review page still listing what the change "would" affect after it was accepted ("they are released if the change is accepted"), and a reload would have worked it out against the new times. The impact is now shown only while the request is pending (A3); TC-70-12, TC-70-27 and TC-70-30 check this, and two breakages (B30, F11) confirm the checks fail without it.

### b. The tests catch broken code (mutation check)

Each mutation breaks one rule, runs the tests, and restores the file byte for byte ([mutations](SCRUM-70/scripts/mutations.py), run with SCRUM-77's runner).

- **Backend: 30/30 caught** ([results](SCRUM-70/mutation-results-backend.txt)), e.g. anyone may decide (B1), another event's request reachable (B2), deciding on a cancelled event (B3), dead bookings listed (B6), released reservations counted (B12), a decided request decided again (B13), no reason needed (B16), 501 characters accepted (B17), invisible-space reasons (B18), a failed save reported as success (B20), the request not locked (B21), values not applied (B24), rejecting applies them (B25), withdrawn attendees told (B27), attendees told of every change (B28), emails tried after the queue failed (B29).
- **Frontend: 11/11 caught** ([results](SCRUM-70/mutation-results-frontend.txt)), e.g. the impact hidden (F1) or kept after deciding (F11), a rejection sent without a reason (F3), a too-long reason sendable (F4), the reason lost on failure (F5), the organiser not shown the outcome (F9) or the reason (F10).

### c. The running app does what it says (end-to-end)

The real app (Vite → Flask → the local PostgreSQL) driven in Microsoft Edge by [e2e_check.mjs](SCRUM-70/scripts/e2e_check.mjs), on events from [seed_demo_change_reviews.py](SCRUM-70/scripts/seed_demo_change_reviews.py):

| Check | What | Screenshot |
|---|---|---|
| E2E-01 | From "Change requests to review", the coordinator opens the request to move the gala a day later and sees its confirmed booking, 2 reserved microphones and 2 registered attendees affected (AC1, AC2) | [01](SCRUM-70/01-review-impact.png) |
| E2E-02 | Another coordinator gets 403, without the request's details (AC1) | — |
| E2E-03 | Accepting confirms it (equipment released, organiser and 2 attendees told), hides the impact, and the planning view shows the new times (AC3, AC8) | [02](SCRUM-70/02-accepted.png), [03](SCRUM-70/03-planning-new-times.png) |
| E2E-04 | Both registered attendees have a notification with the new date, time and venue; the attendee who withdrew has none (AC9) | — |
| E2E-05 | Rejecting with no reason is refused; 501 characters disables Reject; nothing saved (AC4) | [04](SCRUM-70/04-reason-too-long.png) |
| E2E-06 | A failed save (request aborted) says so, keeps the reason, saves nothing (AC6) | [05](SCRUM-70/05-save-failed.png) |
| E2E-07 | Rejecting with a reason; the organiser's page shows Rejected with the reason; the organiser has both decision notifications (AC3, AC4, AC7) | [06](SCRUM-70/06-organiser-sees-rejection.png) |
| E2E-08 | An approved event waiting for a coordinator tells the organiser so and offers no form (AC5) | [07](SCRUM-70/07-waiting-for-coordinator.png) |

**Runs.** The first run failed E2E-01 because the script read the list before the page had loaded (`allInnerTexts` doesn't wait); it now waits for the list. The second run passed 8/8 and its screenshots showed the stale impact described in §3a. After that fix, a third run on freshly seeded events passed 8/8; the screenshots are from it.

### d. Findings for the team (not part of SCRUM-70)

1. **SCRUM-52's next step (SCRUM-46 Q7) is still open.** `PATCH /api/events/<id>` still points the coordinator at the organiser-only change request endpoint. SCRUM-70 doesn't change who submits; the team decision is still needed.
2. **Accepted new times leave venue bookings on the old date** (Q3; [03](SCRUM-70/03-planning-new-times.png)). The coordinator sees them listed as affected before accepting and rebooks with SCRUM-85/94. If the customer wants bookings moved or cancelled automatically, that is a change to this story.
3. **SCRUM-63's venue tests assume an empty `venues` table.** A whole-suite run on the database the browser check had seeded (demo venues committed) failed 5 of them in `test_venue_catalogue` and `test_venue_details`; on a freshly built database all pass. Already known for Supabase, which holds real venues.

### e. Limitations

- **Against Supabase, only the schema check and the SCRUM-46/70 tests were run** (73/73 pass, see the note at the top). The whole suite was run against the local database, as CI does.
- **Concurrency is shown, not stress-tested.** TC-70-18 confirms the event, then the request, are read `FOR UPDATE` before anything is written; two decisions at the same moment were not run in parallel.
- **Emails were queued, not delivered:** tests patch the queue, and the browser check ran without a Celery worker.
- The demo accounts and events used in the browser check exist in the local database only.

## 4. Evidence documented

- This document, and the test-case document with its traceability matrix and open questions.
- [SCRUM-70/](SCRUM-70/): screenshots `01`–`07`; `scripts/` (seed script, browser check, mutations); `mutation-results-backend.txt`, `mutation-results-frontend.txt`, `e2e-results.txt`.
- Commits: `dae9123` (TDD, red), `8d2051f` (TDD, green) and the follow-up that hides the impact once a request is decided.
