# SCRUM-78 — Reject Event Request: Definition of Done Evidence

**Story:** As an Event Coordinator, I want to reject a submitted event request with a reason so that the Event Organiser understands why the event cannot proceed.

**Branch:** `feature/SCRUM-78-reject-event-request` · **Checked:** 12 Oct 2026 · **Test cases:** [SCRUM-78-reject-event-request.md](../test-cases/SCRUM-78-reject-event-request.md) · **Screenshots and scripts:** [SCRUM-78/](SCRUM-78/)

| # | Definition of Done item | Result |
|---|---|---|
| 1 | Acceptance criteria satisfied | ✅ All 6 ACs met, each shown by automated tests and in the running app ([§1](#1-acceptance-criteria-satisfied)) |
| 2 | All test cases pass | ✅ Backend 407 tests OK (3 skipped, not SCRUM-78), frontend 130/130, end-to-end 8/8 ([§2](#2-all-test-cases-pass)) |
| 3 | Test cases are correct and the code does what it says | ✅ 16/16 deliberate breakages caught; behaviour confirmed in a real browser ([§3](#3-test-cases-are-correct-and-the-code-does-what-it-says)) |
| 4 | Evidence of checks documented | ✅ This document, 4 screenshots and the scripts that produced them ([§4](#4-evidence-documented)) |

## What this story changed

SCRUM-32 already built rejecting, and SCRUM-60 tightened the reason rules. Re-checking them against SCRUM-78's ACs found **no behaviour to change**. It did find **gaps in the tests**, which this story closes:

- **Roles:** the who-may-decide tests (TC-32-02, 03) only ever tried *approving*. No test tried rejecting as a non-coordinator.
- **Under review:** no test checked that an "under review" request cannot be rejected.
- **Order of checks:** no test checked that permission is checked before the reason. In the mutation check, swapping the order was caught only by the new TC-78-04.
- **Saved reason:** no test read the saved reason back through the API, or checked that a refused rejection saves no reason.
- **"My event requests" (SCRUM-59):** never checked after a real rejection.

Files added: `backend/tests/test_reject_event_request.py` (8 tests), the test-case document and this evidence. The frontend's rejection behaviour was already fully tested (see the test-case document). There is no production code change and no schema change.

## 1. Acceptance criteria satisfied

| AC | Criterion | How it is met | Automated tests | Seen in the running app |
|----|-----------|---------------|-----------------|-------------------------|
| AC1 | Only an event request with status Submitted can be rejected. | Any other status gets HTTP 409 naming the status, and nothing changes. The review page shows Reject only for Submitted. | TC-78-01, 02; TC-32-01, 09; TC-77-07 | E2E-06, 07 |
| AC2 | Only an Event Coordinator can reject the request. | Every other role, and every coordinator not assigned to the event, gets HTTP 403, checked before the reason. | TC-78-03, 04; TC-32-04 | E2E-01 |
| AC3 | A non-empty rejection reason is required. | A missing, empty or spaces-only reason (including non-breaking and zero-width spaces) gets HTTP 400 "A reason is required to reject this request." The page says the same without sending. | TC-78-06; TC-32-10, 11; TC-60-12, 13 | E2E-02, 03 · [01](SCRUM-78/01-reason-required.png) |
| AC4 | When rejected, the request status becomes Rejected. | The status is saved as `rejected`, with the decision time and who decided. The page confirms it. | TC-78-02, 05, 07; TC-32-12, 20 | E2E-04 · [02](SCRUM-78/02-rejected-confirmation.png) |
| AC5 | The rejection reason is saved with the request. | The trimmed reason is stored in the same commit and returned with the request. | TC-78-05, 06; TC-32-12 | E2E-04, 05 · [02](SCRUM-78/02-rejected-confirmation.png) |
| AC6 | The Event Organiser can view the rejected status and rejection reason. | Both organiser lists show "Status: Rejected · decided …" and "Reason: …". The notification and email include the reason. | TC-78-07, 08; TC-32-13, 14, 18, 21; TC-59-11 | E2E-08 · [03](SCRUM-78/03-organiser-my-event-requests.png), [04](SCRUM-78/04-organiser-my-requests.png) |

**Assumptions** (open questions in the test-case document):

- **Q1:** only the event's *assigned* coordinator may reject.
- **Q2:** requests that are under review are not rejectable.
- **Q3:** a reason is limited to 1,000 words.

## 2. All test cases pass

| Suite | Command | Result |
|-------|---------|--------|
| Backend, whole suite (what CI runs) | `python -m unittest discover` (from `backend/`) | **Ran 407 tests, OK (skipped=3)** — the skips are in other stories' files |
| Backend, SCRUM-78 | `python -m unittest tests.test_reject_event_request` | **8/8 pass** (TC-78-01 to 08) |
| Backend, reject-related (SCRUM-32/59/60) | `tests.test_event_decisions`, `tests.test_decision_accountability`, `tests.test_my_event_requests` | pass (the mutation-check baseline) |
| Frontend, whole suite | `npm test` (from `frontend/`) | **13 files, 130/130 pass** |
| End-to-end in a real browser | [scripts/e2e_check.mjs](SCRUM-78/scripts/e2e_check.mjs) | **8/8 pass** (§3c) |

Because the behaviour already existed, the new tests passed the first time they ran. §3b shows that they fail when the behaviour breaks.

## 3. Test cases are correct and the code does what it says

### a. The test cases match the acceptance criteria

- Each AC traces to new and existing test cases (traceability matrix in the test-case document). Every new test names its `TC-78-xx` ID.
- The new tests reuse SCRUM-32's seed data and helpers, and assert exact outcomes:
  - the 409 names the status;
  - the 403 contains no event details;
  - nothing is saved, notified or emailed after a refusal;
  - the saved reason is trimmed;
  - the organiser's list items have the exact status, reason, decision time and decider;
  - another organiser's responses do not contain the reason anywhere.

### b. The tests catch broken code (mutation check)

Each row below is a deliberate bug put into the code, one at a time, with the reject-related tests run against it. Every change was reverted afterwards and the tests passed again. Runner: [SCRUM-77/scripts/mutation_check.py](SCRUM-77/scripts/mutation_check.py). Mutations: [scripts/mutations.py](SCRUM-78/scripts/mutations.py).

| ID | Deliberate bug | Should break | Caught? | Failing tests (examples) |
|----|----------------|--------------|---------|--------------------------|
| B1 | Reject a request that is under review | AC1 | ✅ | `test_a_request_under_review_cannot_be_rejected`, `test_only_a_submitted_request_becomes_rejected` |
| B2 | Reject a request in any status | AC1 | ✅ | `test_requests_that_are_not_submitted_cannot_be_decided` (+4) |
| B3 | Let any coordinator reject, not just the assigned one | AC2 | ✅ | `test_no_one_else_can_reject` (+3) |
| B4 | Let any role reject | AC2 | ✅ | `test_no_one_else_can_reject`, `test_permission_is_checked_before_the_reason` (+3) |
| B5 | Check the reason before permission | AC2, AC3 | ✅ | `test_permission_is_checked_before_the_reason` (the only test that catches it) |
| B6 | Reject without a reason | AC3 | ✅ | `test_rejecting_without_a_reason_is_refused` (+2) |
| B7 | Accept a reason made only of spaces | AC3 | ✅ | `test_reasons_made_only_of_spaces_are_refused`, `test_a_refused_rejection_saves_no_reason` (+4) |
| B8 | Rejecting sets the status to "under review" instead of "rejected" | AC4 | ✅ | `test_rejecting_updates_the_status_and_records_the_reason` (+10) |
| B9 | The reason is not saved | AC5 | ✅ | `test_the_reason_is_saved_with_the_request` (+6) |
| B10 | "My requests" hides rejected requests from the organiser | AC6 | ✅ | `test_list_reflects_a_new_decision`, `test_organiser_sees_the_rejection_on_both_lists` (+3) |
| B11 | "My event requests" hides rejected requests from the organiser | AC6 | ✅ | `test_organiser_sees_the_rejection_on_both_lists` (+3) |
| F1 | Review page sends a blank reason instead of refusing it | AC3 | ✅ | says a reason is required when rejecting with only spaces (+4) |
| F2 | Review page's Reject button approves | AC4 | ✅ | rejects with the trimmed reason and shows it (+6) |
| F3 | Review page does not show the saved reason | AC5 | ✅ | rejects with the trimmed reason and shows it (+3) |
| F4 | "My requests" page does not show the reason | AC6 | ✅ | shows each request's status, decision time, and the reason or note |
| F5 | "My event requests" page does not show the reason | AC6 | ✅ | shows drafts and submitted requests in two labelled sections |

**Result: 16/16 caught.**

The first version of F3–F5 deleted the reason line outright. That left empty JSX brackets, so the page failed to compile and the tests failed for the wrong reason (no test names were reported). They were changed to replace the line with an empty paragraph and run again. The table shows that second run, where each failure comes from a test's own assertion.

### c. The running app does what it says (end-to-end)

These checks were run against the real app:

- the Vite dev server and the Flask API;
- the team's Supabase database;
- Redis, from `docker compose up -d redis`. No Celery worker was running, so emails were queued but not sent.

A script drove Microsoft Edge with Playwright. Each run uses fresh `[Demo]` requests from [SCRUM-77/scripts/seed_demo_requests.py](SCRUM-77/scripts/seed_demo_requests.py) and the SCRUM-62 demo accounts.

| ID | Check | Result | Screenshot |
|----|-------|--------|------------|
| E2E-01 | The organiser, and a coordinator not assigned to the request, cannot reject it (HTTP 403), and the organiser sees no Reject button. | PASS | — |
| E2E-02 | The API refuses a missing, empty, spaces-only, or non-breaking/zero-width-space reason with HTTP 400, `field: "reason"` and "A reason is required to reject this request." | PASS | — |
| E2E-03 | Pressing Reject with no reason, or with only spaces, shows that message, and the request stays Submitted. | PASS | [01](SCRUM-78/01-reason-required.png) |
| E2E-04 | Rejecting with a reason (typed with surrounding spaces) shows "Status: Rejected", "Reason: …" and a confirmation, and removes the buttons. | PASS | [02](SCRUM-78/02-rejected-confirmation.png) |
| E2E-05 | After reloading, the request is still Rejected, with the reason trimmed. | PASS | — |
| E2E-06 | Rejecting it again through the API is refused (HTTP 409). | PASS | — |
| E2E-07 | A request under review shows no Reject button, and the API refuses to reject it (HTTP 409, naming `under_review`). | PASS | — |
| E2E-08 | The organiser sees "Status: Rejected · decided …" and "Reason: …" on My event requests and on My requests. | PASS | [03](SCRUM-78/03-organiser-my-event-requests.png), [04](SCRUM-78/04-organiser-my-requests.png) |

**First run: 7/8.** E2E-01 failed in the first run, and the cause was the environment, not SCRUM-78. The Flask server had been idle for about 13 hours. The demo organiser's login, the first database query after that, failed with HTTP 503, and the script went on without a token, which got HTTP 422. Repeating the same calls by hand gave the expected 403s. The script now stops if a login fails. A second run on fresh requests passed 8/8; the screenshots are from that run.

### d. Findings for the team (not part of SCRUM-78)

1. **The first request after a long idle period fails.** SQLAlchemy reuses pooled connections to Supabase, and after hours idle the first one used is dead. That request then fails with HTTP 503, as the demo organiser's login did here. The app does not set `pool_pre_ping`. A one-line fix would make SQLAlchemy test each connection before use: `SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}` in `Config`. This is shared config, so it was not changed here.
2. **Without Redis, approving or rejecting takes about 110 seconds to respond** (reported in [SCRUM-77 evidence §3d](SCRUM-77-dod-evidence.md#d-finding-for-the-team-not-part-of-scrum-77)). It applies to rejecting in the same way.

### e. Limitations

- The end-to-end script and the mutation check are not part of CI.
- The demo data is shared, so the organiser's list also shows `[Demo]` rows from earlier runs.

## 4. Evidence documented

- **This document:** [docs/evidence/SCRUM-78-dod-evidence.md](SCRUM-78-dod-evidence.md).
- **Screenshots:** [docs/evidence/SCRUM-78/](SCRUM-78/), files `01`–`04`.
- **Scripts:** [docs/evidence/SCRUM-78/scripts/](SCRUM-78/scripts/).
  - `mutations.py` holds the mutations, run with the SCRUM-77 runner.
  - `e2e_check.mjs` runs the end-to-end check.
- **Test cases and traceability:** [docs/test-cases/SCRUM-78-reject-event-request.md](../test-cases/SCRUM-78-reject-event-request.md).
