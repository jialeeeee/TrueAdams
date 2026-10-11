# SCRUM-77 — Approve Event Request: Definition of Done Evidence

**Story:** As an Event Coordinator, I want to approve a submitted event request so that a feasible event can proceed to further planning.

**Branch:** `feature/SCRUM-77-approve-event-request` · **Checked:** 12 Oct 2026 · **Test cases:** [SCRUM-77-approve-event-request.md](../test-cases/SCRUM-77-approve-event-request.md) · **Screenshots and scripts:** [SCRUM-77/](SCRUM-77/)

| # | Definition of Done item | Result |
|---|---|---|
| 1 | Acceptance criteria satisfied | ✅ All 4 ACs met, each shown by automated tests and in the running app ([§1](#1-acceptance-criteria-satisfied)) |
| 2 | All test cases pass | ✅ Backend 399 tests OK (3 skipped, not SCRUM-77), frontend 130/130, end-to-end 8/8 ([§2](#2-all-test-cases-pass)) |
| 3 | Test cases are correct and the code does what it says | ✅ 13/13 deliberate breakages caught; behaviour confirmed in a real browser ([§3](#3-test-cases-are-correct-and-the-code-does-what-it-says)) |
| 4 | Evidence of checks documented | ✅ This document, 6 screenshots and the scripts that produced them ([§4](#4-evidence-documented)) |

## What this story changed

SCRUM-32 already built approving (`POST /api/events/<id>/decision`, the review page, the organiser's lists), and SCRUM-60 hardened it. Re-checking it against SCRUM-77's ACs found **no behaviour to change**. It did find **gaps in the tests**, which this story closes:

- **Under review:** no test checked that an "under review" request cannot be approved.
- **Organiser's view after a real approval:** no test approved a request and then read the organiser's lists. The existing list tests only used rows seeded as approved.
- **Review page buttons:** no frontend test checked that statuses other than Submitted get no Approve button.

Files added or changed:

- `backend/tests/test_approve_event_request.py` (new, 6 tests);
- a SCRUM-77 block in `frontend/src/pages/ReviewRequestPage.test.jsx` (5 tests);
- the test-case document;
- this evidence.

There is no production code change and no schema change.

## 1. Acceptance criteria satisfied

| AC | Criterion | How it is met | Automated tests | Seen in the running app |
|----|-----------|---------------|-----------------|-------------------------|
| AC1 | Only an event request with status Submitted can be approved. | Any other status gets HTTP 409 naming the status, and nothing changes. The review page shows Approve only for Submitted. | TC-77-01, 02, 07, 08; TC-32-01, 09 | E2E-01, 04, 05 · [01](SCRUM-77/01-submitted-request-before-approval.png), [03](SCRUM-77/03-under-review-no-approve.png) |
| AC2 | Only an Event Coordinator can approve the request. | Every other role gets HTTP 403. So does a coordinator who is not assigned to the event (stricter than the AC; see Q1). | TC-77-03; TC-32-02, 03, 04 | E2E-06, 07 · [04](SCRUM-77/04-organiser-refused.png) |
| AC3 | When approved, the request status becomes Approved. | The status is saved as `approved`, with the decision time and who decided. The page confirms it. | TC-77-02, 04; TC-32-07, 08 | E2E-02, 03 · [02](SCRUM-77/02-approved-confirmation.png) |
| AC4 | The Event Organiser can view the approved status. | Both organiser lists show "Status: Approved · decided …" and "Decided by …". | TC-77-04, 05, 06; TC-32-17, 21; TC-59-11 | E2E-08 · [05](SCRUM-77/05-organiser-my-event-requests.png), [06](SCRUM-77/06-organiser-my-requests.png) |

**Assumptions** (open questions in the test-case document):

- **Q1:** only the event's *assigned* coordinator may approve, as SCRUM-32 built it. The AC says "an Event Coordinator".
- **Q2:** requests that are under review are not approvable.

## 2. All test cases pass

| Suite | Command | Result |
|-------|---------|--------|
| Backend, whole suite (what CI runs) | `python -m unittest discover` (from `backend/`) | **Ran 399 tests, OK (skipped=3)** — the skips are in other stories' files |
| Backend, SCRUM-77 | `python -m unittest tests.test_approve_event_request` | **6/6 pass** (TC-77-01 to 06) |
| Backend, approve-related (SCRUM-32/59) | `tests.test_event_decisions`, `tests.test_my_event_requests` | pass (the mutation-check baseline) |
| Frontend, whole suite | `npm test` (from `frontend/`) | **13 files, 130/130 pass** |
| End-to-end in a real browser | [scripts/e2e_check.mjs](SCRUM-77/scripts/e2e_check.mjs) | **8/8 pass** (§3c) |

Because the behaviour already existed, the new tests passed the first time they ran; there was no TDD red phase. §3b shows that they still fail when the behaviour breaks.

## 3. Test cases are correct and the code does what it says

### a. The test cases match the acceptance criteria

- Each AC traces to new and existing test cases (traceability matrix in the test-case document). Every new test names its `TC-77-xx` ID.
- The new backend tests reuse SCRUM-32's seed data and helpers (`DecisionTestCase`), so they check the same rows the same way.
- They assert exact outcomes:
  - the 409 names the status;
  - nothing is saved, notified or emailed after a refusal;
  - the organiser's list items have the exact status, decision time and decider;
  - another organiser cannot see the approval.

### b. The tests catch broken code (mutation check)

Each row below is a deliberate bug put into the code, one at a time, with the approve-related tests run against it. Every change was reverted afterwards and the tests passed again. Script: [scripts/mutation_check.py](SCRUM-77/scripts/mutation_check.py). Mutations: [scripts/mutations.py](SCRUM-77/scripts/mutations.py).

| ID | Deliberate bug | Should break | Caught? | Failing tests (examples) |
|----|----------------|--------------|---------|--------------------------|
| B1 | Approve a request that is under review | AC1 | ✅ | `test_a_request_under_review_cannot_be_approved`, `test_only_a_submitted_request_becomes_approved` |
| B2 | Approve a request in any status | AC1 | ✅ | `test_requests_that_are_not_submitted_cannot_be_decided` (+3) |
| B3 | Let any coordinator approve, not just the assigned one | AC2 | ✅ | `test_only_the_assigned_coordinator_can_decide` (+2) |
| B4 | Let any role approve | AC2 | ✅ | `test_no_other_role_can_approve` (+3) |
| B5 | Approving sets the status to "under review" instead of "approved" | AC3 | ✅ | `test_approving_updates_the_status_to_approved` (+5) |
| B6 | Approval saved but never committed | AC3 | ✅ | `test_failed_save_changes_nothing_and_retry_works` |
| B7 | "My requests" hides approved requests from the organiser | AC4 | ✅ | `test_organiser_sees_the_approval_on_both_lists`, `test_organisers_list_of_event_requests` |
| B8 | "My event requests" hides approved requests from the organiser | AC4 | ✅ | `test_organiser_sees_the_approval_on_both_lists` (+3) |
| F1 | Review page offers Approve for any undecided status | AC1 | ✅ | offers no Approve button for a draft / under_review / cancelled request |
| F2 | Review page ignores the server's refusal | AC1 | ✅ | shows the server's refusal when the request is no longer submitted (+10) |
| F3 | Review page keeps showing Submitted after approving | AC3 | ✅ | approves, shows Approved, and removes the buttons (+5) |
| F4 | "My requests" page drops the status | AC4 | ✅ | shows each request's status, decision time, and the reason or note |
| F5 | "My event requests" page drops the status | AC4 | ✅ | shows drafts and submitted requests in two labelled sections |

**Result: 13/13 caught.** B6 is only caught by a test that makes the save fail. The test database runs each test inside a transaction, so a missing commit is otherwise invisible to it, and the end-to-end check (E2E-03, reload after approving) is what shows that the approval is really saved.

### c. The running app does what it says (end-to-end)

These checks were run against the real app:

- the Vite dev server and the Flask API;
- the team's Supabase database;
- Redis, started with `docker compose up -d redis`. No Celery worker was running, so emails were queued but not sent.

A script drove Microsoft Edge with Playwright. Each run uses fresh `[Demo]` requests from [scripts/seed_demo_requests.py](SCRUM-77/scripts/seed_demo_requests.py) and the SCRUM-62 demo accounts.

| ID | Check | Result | Screenshot |
|----|-------|--------|------------|
| E2E-01 | A submitted request offers Approve to its coordinator. | PASS | [01](SCRUM-77/01-submitted-request-before-approval.png) |
| E2E-02 | Clicking Approve changes the status to Approved, confirms it (naming the organiser notified) and removes the buttons. | PASS | [02](SCRUM-77/02-approved-confirmation.png) |
| E2E-03 | After reloading, the request is still Approved, with "Decided by" the coordinator. | PASS | — |
| E2E-04 | Approving it again through the API is refused (HTTP 409). | PASS | — |
| E2E-05 | A request under review shows no Approve button, and the API refuses to approve it (HTTP 409, naming `under_review`). | PASS | [03](SCRUM-77/03-under-review-no-approve.png) |
| E2E-06 | The organiser cannot open the review page, and the API refuses their approval (HTTP 403). | PASS | [04](SCRUM-77/04-organiser-refused.png) |
| E2E-07 | A coordinator not assigned to the request cannot open it or approve it (HTTP 403). | PASS | — |
| E2E-08 | The organiser sees "Status: Approved · decided …" and "Decided by …" on My event requests, and Approved on My requests. | PASS | [05](SCRUM-77/05-organiser-my-event-requests.png), [06](SCRUM-77/06-organiser-my-requests.png) |

### d. Finding for the team (not part of SCRUM-77)

**Approving takes about 110 seconds when Redis is not running.** In the first end-to-end run, Redis was not running. The approval was saved at once, but the page waited about 110 seconds for a reply (clicked 01:47:01, reply after "Could not queue decision email" at 01:48:50). During that time Celery kept retrying the connection to Redis before reporting `email_queued: false`.

- **Where it applies:** every action that queues an email: approve and reject (SCRUM-32/60) and clarification requests (SCRUM-31).
- **Why the tests missed it:** they replace the email queue with a mock.
- **Suggested fix:** a short Celery publish timeout and retry limit in `create_app`. This is shared code, so it was not changed here; it should be agreed by the team or raised as its own story.
- **Re-run:** with Redis running, all 8 checks passed and approving answered at once.

### e. Limitations

- The end-to-end script and the mutation check are not part of CI.
- The demo data is shared, so the organiser's list also shows `[Demo]` rows from earlier runs.

## 4. Evidence documented

- **This document:** [docs/evidence/SCRUM-77-dod-evidence.md](SCRUM-77-dod-evidence.md).
- **Screenshots:** [docs/evidence/SCRUM-77/](SCRUM-77/), files `01`–`06`.
- **Scripts:** [docs/evidence/SCRUM-77/scripts/](SCRUM-77/scripts/).
  - `mutation_check.py` and `mutations.py` run the mutation check (`python mutation_check.py mutations.py backend|frontend`, from the repo root).
  - `seed_demo_requests.py` adds fresh demo requests.
  - `e2e_check.mjs` runs the end-to-end check.
- **Test cases and traceability:** [docs/test-cases/SCRUM-77-approve-event-request.md](../test-cases/SCRUM-77-approve-event-request.md).
