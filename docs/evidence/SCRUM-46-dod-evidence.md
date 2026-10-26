# SCRUM-46 — Submit Change Request for a Submitted Event: Definition of Done Evidence

**Story:** As an Event Organiser, I want to request a change to an event I have submitted so that ConnectSphere can assess my updated needs before existing arrangements are altered.

**Branch:** `feature/SCRUM-46-change-request` (from `main` at `93bd846`) · **Checked:** 27 Oct 2026 · **Test cases:** [SCRUM-46-change-request.md](../test-cases/SCRUM-46-change-request.md) · **Screenshots, scripts and raw results:** [SCRUM-46/](SCRUM-46/)

| # | Definition of Done item | Result |
|---|---|---|
| 1 | Acceptance criteria satisfied | ✅ All 9 ACs met, each shown by automated tests and in the running app ([§1](#1-acceptance-criteria-satisfied)) |
| 2 | All test cases pass | ✅ SCRUM-46 backend 34/34 and frontend 11/11; whole backend suite 1010 run, all pass (3 skipped, not SCRUM-46's); whole frontend suite 479/479; end-to-end 8/8 ([§2](#2-all-test-cases-pass)) |
| 3 | Test cases are correct and the code does what it says | ✅ Written test-first (red, then green); 32/32 deliberate breakages caught; behaviour confirmed in a real browser ([§3](#3-test-cases-are-correct-and-the-code-does-what-it-says)) |
| 4 | Evidence of checks documented | ✅ This document, 6 screenshots, the scripts that produced them and the raw results ([§4](#4-evidence-documented)) |

> **Before merging:** run `backend/db/event_change_requests.sql`, then the updated `backend/db/test_role.sql`, in the Supabase SQL editor as the project owner. Until then `test_database_tables_match_the_models` fails against Supabase (CI's `supabase-schema` job) and every SCRUM-46 API test fails there. All the results below come from a local PostgreSQL 17 built by `ci/build_test_database.py`, as CI's `unittest` job builds it, with the tests logged in as the restricted `connectsphere_test` role.

## What this story changed

- **Database:** a new `event_change_requests` table (`backend/db/event_change_requests.sql`): the event, the organiser who asked and when, status `pending_review`, and `changes` as `{field: {"from", "to"}}`. A partial unique index allows one pending request per event. `test_role.sql` gives the test role the new table.
- **Backend:**
  - `GET` and `POST /api/events/<id>/change-requests`, replacing the 501 stub at the same URL and function name, so SCRUM-52's `requires_review.next_step` still points here. The POST locks the event, checks it (approved, has a coordinator, nothing pending), checks every proposed value, and saves the request and the coordinator's notification in one commit; the email is queued after it.
  - The proposal rules in `backend/app/events/change_requests.py`, free of Flask and the database like `equipment.py`.
  - `tests/test_routes.py` no longer lists the change-requests URL as a stub.
- **Frontend:** the Request a change page (`/events/:id/change-request`), linked as "Request a change" from the organiser's approved requests on My event requests.
- **Docs:** the test-case document; AGENTS.md's stub list; the C4 container diagram lists event change requests among the stored entities.

## 1. Acceptance criteria satisfied

| AC | Criterion | How it is met | Automated tests | Seen in the running app |
|----|-----------|---------------|-----------------|-------------------------|
| AC1 | I can request a change only for my own events whose status is Approved. | Only the event's organiser, and only for `approved` events. Others get 403 without the event's details; other statuses get 409 naming the status, and the form says why. The link appears only on approved requests. | TC-46-01 to 03, 21, 24, 27 | E2E-01, 08 · [01](SCRUM-46/01-change-request-form.png) |
| AC2 | I can propose new values for the permitted fields: date, time, expected attendance, venue requirements and equipment requirements. | Start, end, expected attendance, venue requirements and equipment requirements, prefilled with the current values. Only what changed is sent and recorded. | TC-46-01, 04, 05, 06, 11, 21, 22 | E2E-01, 04 |
| AC3 | Each request records the event, the affected fields and the proposed values. | One row per request: the event, who and when, and each affected field with its current and proposed value. | TC-46-04, 05, 07 | E2E-04 · [04](SCRUM-46/04-pending-review.png) |
| AC4 | If a change is disallowed or invalid, submission is blocked and the reason is shown. | 422 naming every problem at once: fields that can't be changed this way, attendance that isn't a whole number of at least 1, an end not after the start (checked against the current start or end when only one changes), invalid dates, blank venue requirements, text too long, or no change at all. The page shows each reason by its field and keeps the entries. | TC-46-06, 08 to 11, 23 | E2E-02 · [02](SCRUM-46/02-invalid-refused.png) |
| AC5 | If the event has no assigned coordinator, submission is blocked and I'm told why. | 409 `no_coordinator`: "This event has no coordinator yet, so there is nobody to review a change request…". The form isn't offered. | TC-46-12, 24 | E2E-07 · [06](SCRUM-46/06-no-coordinator.png) |
| AC6 | On success, the request is saved with status "Pending Review" and a confirmation is shown. | Status `pending_review`, shown as "Pending Review", with a confirmation naming the event and fields. One request at a time: another waits (409 `pending`), and the page shows the pending one. | TC-46-13 to 15, 22, 25 | E2E-04, 05 · [04](SCRUM-46/04-pending-review.png), [05](SCRUM-46/05-already-pending.png) |
| AC7 | The approved event information is not overwritten by a pending request. | The event row is never written by this flow. | TC-46-16 | E2E-05 |
| AC8 | If saving fails, the event and request state are unchanged and an error message is shown. | The request and notification are saved in one commit. A failed save: 503, "Your change request was not submitted, and the event is unchanged. Please try again.", nothing saved, no email. The page keeps the entries for a retry. | TC-46-17, 18, 26 | E2E-03 · [03](SCRUM-46/03-save-failed.png) |
| AC9 | The event's coordinator is notified of the pending change request with the proposed changes. | An in-app `change_requested` notification naming each field with its current and proposed value, saved with the request, then an email. If the email can't be queued, the request still stands (`email_queued: false`). | TC-46-19, 20 | E2E-06 |

**Working assumptions.** Each is tied to an open question in the test-case document; none has been agreed with the customer:

- **Q1:** only approved events (the story's title says "Submitted Event").
- **Q2:** equipment requirements are the organiser's own note, not SCRUM-42's itemised list.
- **Q3:** the venue and whether registration is needed can't be changed this way.
- **Q4:** past dates aren't refused, as in SCRUM-29.
- **Q5:** one pending request per event.
- **Q6:** deciding and applying a request is a later story.
- **Q7:** only the organiser can submit, although SCRUM-52 tells the coordinator to submit one.

## 2. All test cases pass

| Suite | Command | Result |
|-------|---------|--------|
| Backend, SCRUM-46 through the API | `python -m unittest tests.test_change_requests` (from `backend/`) | **20/20 pass** (TC-46-01 to 20) |
| Backend, SCRUM-46 rules (no database) | `python -m unittest tests.test_change_requests_unit` | **14/14 pass** |
| Backend, whole suite | `python -m unittest discover` | **Ran 1010 tests: OK, 3 skipped.** The skips are SCRUM-36/37 tests waiting on customer answers. Includes SCRUM-52's and SCRUM-59's tests. |
| Frontend, SCRUM-46 | `npx vitest run src/pages/ChangeRequestPage.test.jsx src/pages/MyEventRequestsPage.test.jsx` | **11/11 pass**: the page 10, the link 1 (23/23 across the two files) |
| Frontend, whole suite | `npm test` (from `frontend/`) | **479/479 pass** |
| End-to-end in a real browser | [scripts/e2e_check.mjs](SCRUM-46/scripts/e2e_check.mjs) | **8/8 pass** (§3c), [raw result](SCRUM-46/e2e-results.txt) |

## 3. Test cases are correct and the code does what it says

### a. The test cases match the acceptance criteria

Every AC has at least one API test and, where the user sees it, a page test (traceability matrix in the test-case document). The tests were written first and committed failing (`2e0a3de`, "TDD, red"): the API tests failed on the 501 stub, the rules tests on the missing module, the page tests on an empty page.

While making them pass, two API tests turned out to contradict assumption A4 (they moved only the start to after the current end). The rule was right; the test data was changed to an earlier start, in the tests and the document alike.

### b. The tests catch broken code (mutation check)

Each mutation breaks one rule, runs the tests, and restores the file byte for byte ([mutations](SCRUM-46/scripts/mutations.py), run with SCRUM-77's runner).

- **Backend: 21/21 caught** ([results](SCRUM-46/mutation-results-backend.txt)), e.g. anyone may request (B1), non-approved events accepted (B2), no coordinator accepted (B3), negative attendance (B5), an end equal to the start (B7), the request applied to the event (B16), no notification (B19), a failed save reported as success (B17).
- **Frontend: 11/11 caught** ([results](SCRUM-46/mutation-results-frontend.txt)), e.g. every field sent (F1), field reasons not shown (F3), entries lost (F4), the form shown when blocked (F5), the link on every request (F11).

### c. The running app does what it says (end-to-end)

The real app (Vite → Flask → the local PostgreSQL) driven in Microsoft Edge by [e2e_check.mjs](SCRUM-46/scripts/e2e_check.mjs), on events from [seed_demo_change_requests.py](SCRUM-46/scripts/seed_demo_change_requests.py):

| Check | What | Screenshot |
|---|---|---|
| E2E-01 | From My event requests, only the approved event has "Request a change"; the form shows its current values and coordinator (AC1, AC2) | [01](SCRUM-46/01-change-request-form.png) |
| E2E-02 | Attendance -5 and an end before the start are refused, each reason by its field; nothing saved (AC4) | [02](SCRUM-46/02-invalid-refused.png) |
| E2E-03 | A failed save (request aborted) says so and keeps the entries; nothing saved (AC8) | [03](SCRUM-46/03-save-failed.png) |
| E2E-04 | A valid request: "Pending Review", confirmation, both changes listed (AC2, AC3, AC6) | [04](SCRUM-46/04-pending-review.png) |
| E2E-05 | The coordinator's planning view still shows the approved values; the form now says a request is pending (AC6, AC7) | [05](SCRUM-46/05-already-pending.png) |
| E2E-06 | The coordinator's notification names the event and both changes (AC9) | — |
| E2E-07 | An approved event with no coordinator says why and offers no form (AC5) | [06](SCRUM-46/06-no-coordinator.png) |
| E2E-08 | A submitted event can't take a request, even by its address; the coordinator gets 403 (AC1) | — |

**First two runs failed because of the script, not the app.** Playwright's `getByLabel("End")` also matched "Expected att**end**ance", and after reseeding, two events had the same title. The script now matches labels exactly and finds events by ID. The third run, on freshly seeded events, passed 8/8; the screenshots are from that run.

### d. Findings for the team (not part of SCRUM-46)

1. **SCRUM-52 points the coordinator at an organiser-only endpoint (Q7).** `PATCH /api/events/<id>` (coordinator) answers a restricted change with `requires_review.next_step` → `POST /api/events/<id>/change-requests`, but SCRUM-46's AC1 lets only the organiser submit there, so the coordinator gets 403. SCRUM-52 was not changed; the team needs to decide whether coordinators may also submit change requests.
2. **SCRUM-59's test was narrowed.** `MyEventRequestsPage.test.jsx` asserted that submitted requests have no links at all. SCRUM-59's rule (A5) is that they have no link to the *draft editor*, which is still checked; the test now allows only the new "Request a change" link.

### e. Limitations

- **Not yet run against Supabase.** The new table must be created there first (see the note at the top). After the scripts are run, `python -m unittest tests.test_app_factory tests.test_change_requests` against Supabase should be run once before merging.
- **Concurrency is shown, not stress-tested.** TC-46-15 confirms the event is read `FOR UPDATE` before pending requests are looked for, and the unique index refuses a second pending request in any case. Two submissions at the same moment were not simulated.
- The demo accounts and events used in the browser check exist in the local database only.

## 4. Evidence documented

- This document, and the test-case document with its traceability matrix and open questions.
- [SCRUM-46/](SCRUM-46/): screenshots `01`–`06`; `scripts/` (seed script, browser check, mutations); `mutation-results-backend.txt`, `mutation-results-frontend.txt`, `e2e-results.txt`.
- Commits: `2e0a3de` (TDD, red) and the TDD-green commit that follows it on this branch.
