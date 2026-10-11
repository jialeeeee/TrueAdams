# SCRUM-62 — Identify My Managed Events: Definition of Done Evidence

**Story:** As an Event Coordinator, I want a list of the events I manage, with each event's status, so that I can quickly find the event I need and see what stage it is at.

**Branch:** `feature/SCRUM-62-managed-events-list` · **Checked:** 11–12 Oct 2026 · **Test cases:** [SCRUM-62-managed-events-list.md](../test-cases/SCRUM-62-managed-events-list.md) · **Screenshots and scripts:** [SCRUM-62/](SCRUM-62/)

| # | Definition of Done item | Result |
|---|---|---|
| 1 | Acceptance criteria satisfied | ✅ All 5 ACs met, each shown by automated tests and in the running app ([§1](#1-acceptance-criteria-satisfied)) |
| 2 | All test cases pass | ✅ Backend 393 tests OK (3 skipped, not SCRUM-62), frontend 125/125, end-to-end 10/10 ([§2](#2-all-test-cases-pass)) |
| 3 | Test cases are correct and the code does what it says | ✅ 17/17 deliberate breakages caught by the tests; behaviour confirmed in a real browser ([§3](#3-test-cases-are-correct-and-the-code-does-what-it-says)) |
| 4 | Evidence of checks documented | ✅ This document, 8 screenshots and the scripts that produced them ([§4](#4-evidence-documented)) |

## What was built

- **API:** `GET /api/events/managed` in [backend/app/events/routes.py](../../backend/app/events/routes.py) returns the caller's assigned events (`id`, `title`, `start_time`, `status`), soonest first, with an empty-state `message`. Coordinators only (403 otherwise), 401 without a session, 503 `retryable` on a database failure.
- **Pages:** [ManagedEventsPage.jsx](../../frontend/src/pages/ManagedEventsPage.jsx) at `/events/managed` (nav link "My managed events"), and [EventPlanningPage.jsx](../../frontend/src/pages/EventPlanningPage.jsx) at `/events/<id>/planning`, the first screen for the SCRUM-34 planning view.
- **No schema change:** nothing needs to be run on Supabase before merging.

## 1. Acceptance criteria satisfied

| AC | Criterion | How it is met | Automated tests | Seen in the running app |
|----|-----------|---------------|-----------------|-------------------------|
| AC1 | The coordinator can view a list of the events assigned to them, showing each event's name, proposed date and status. | The list shows name, "Proposed date" (start, Singapore time as recorded) and "Status", for the caller's events only. | TC-62-01 to 05, 11 | E2E-01, E2E-02 · [01](SCRUM-62/01-managed-events-list.png) |
| AC2 | Opening an event from the list shows its planning information. | Each name links to `/events/<id>/planning`, which loads the SCRUM-34 planning view. | TC-62-06, 07, 12 | E2E-03, E2E-06 · [02](SCRUM-62/02-planning-fully-recorded.png) |
| AC3 | The event's planning view shows its current status and assigned coordinator. | "Status: …" and "Coordinator: …" under the heading, and in the field list. | TC-62-06, 14 | E2E-03 · [02](SCRUM-62/02-planning-fully-recorded.png), [03](SCRUM-62/03-planning-partly-recorded.png) |
| AC4 | If the coordinator has no assigned events, an empty-state message is shown. | "You have no events assigned to you yet." | TC-62-08, 13 | E2E-09 · [07](SCRUM-62/07-empty-state.png) |
| AC5 | Planning fields with no recorded value are shown as "Not recorded" rather than left blank. | Every `null` field shows "Not recorded", on the list (name, date) and the planning view (all 16 fields). Registration "No" stays "No". | TC-62-09, 12, 15 | E2E-04, E2E-05 · [03](SCRUM-62/03-planning-partly-recorded.png), [04](SCRUM-62/04-planning-nothing-recorded.png) |

**Assumptions the ACs do not settle** (to confirm with the customer; recorded as Q1–Q3 in the test-case document):

- **Q1:** only coordinators have this list; admins get 403.
- **Q2:** cancelled and decided events stay in the list.
- **Q3:** the list is ordered soonest proposed date first, with undated events last.

## 2. All test cases pass

| Suite | Command | Result |
|-------|---------|--------|
| Backend, whole suite (what CI runs) | `python -m unittest discover` (from `backend/`) | **Ran 393 tests, OK (skipped=3)** — the skips are in other stories' files |
| Backend, SCRUM-62 | `python -m unittest tests.test_managed_events` | **10/10 pass** (TC-62-01 to 10) |
| Frontend, whole suite | `npm test` (from `frontend/`) | **13 files, 125/125 pass** |
| Frontend, SCRUM-62 | `ManagedEventsPage.test.jsx`, `EventPlanningPage.test.jsx` | **12/12 pass** (TC-62-11 to 16) |
| End-to-end in a real browser | [scripts/e2e_check.mjs](SCRUM-62/scripts/e2e_check.mjs) | **10/10 pass** (§3c) |

The backend tests were also run before the endpoint existed and failed with HTTP 404 (TDD red), as expected.

## 3. Test cases are correct and the code does what it says

### a. The test cases match the acceptance criteria

- Every AC traces to at least two test cases (traceability matrix in the test-case document). Each test names its `TC-62-xx` ID.
- The backend tests check exact values, not just status codes:
  - the full payload of one event;
  - the exact order of the list;
  - `null` for a blank name and a missing date;
  - that refusals contain no event titles.
- They use only rows they create, so real data in Supabase cannot make them pass or fail.
- The frontend tests use responses that mirror the backend contract and query the page by role and visible text, as a user would.

### b. The tests catch broken code (mutation check)

Each row below is a deliberate bug put into the finished code, one at a time, with the SCRUM-62 tests run against it. A test that still passed would mean it checks nothing. Every change was reverted afterwards and the tests passed again. Script: [scripts/mutation_check.py](SCRUM-62/scripts/mutation_check.py).

| ID | Deliberate bug | Should break | Caught? | Failing tests (examples) |
|----|----------------|--------------|---------|--------------------------|
| B1 | List every event, not just the caller's | AC1 | ✅ | `test_coordinator_sees_only_the_events_assigned_to_them` (+6) |
| B2 | Let any role load the list | AC1 | ✅ | `test_only_coordinators_with_a_valid_session` |
| B3 | Order by ID instead of proposed date | AC1 | ✅ | `test_events_are_listed_soonest_first_with_undated_last` |
| B4 | Send the end time as the proposed date | AC1 | ✅ | `test_each_event_shows_its_name_proposed_date_and_status` |
| B5 | Send a blank name as-is instead of "not recorded" | AC5 | ✅ | `test_blank_name_and_missing_date_are_null` |
| B6 | No empty-state message | AC4 | ✅ | `test_coordinator_with_no_events_gets_an_empty_state_message` |
| B7 | Database failure not caught | load failure | ✅ | `test_load_failure_is_reported_and_retry_works` |
| F1 | List shows a missing name as blank | AC5 | ✅ | shows a missing name and proposed date as Not recorded |
| F2 | List links to the review page, not planning | AC2 | ✅ | opens each event's planning page |
| F3 | List drops the status | AC1 | ✅ | lists each event with its name, proposed date and status |
| F4 | List converts the proposed date through the browser's time zone | AC1 | ✅ | lists each event with its name, proposed date and status |
| F5 | List hides the empty-state message | AC4 | ✅ | shows the empty state when no events are assigned |
| F6 | Planning view shows unrecorded fields as blank | AC5 | ✅ | shows unrecorded fields as Not recorded, never blank |
| F7 | Planning view treats registration "No" as not recorded | AC5 | ✅ | shows unrecorded fields as Not recorded, never blank |
| F8 | Planning view drops the coordinator | AC3 | ✅ | shows the event's status and assigned coordinator |
| F9 | Planning view drops the status | AC3 | ✅ | shows the event's status and assigned coordinator |
| F10 | Planning view offers Retry after a refusal | load failure | ✅ | shows a refusal without a Retry button |

**Result: 17/17 caught.**

### c. The running app does what it says (end-to-end)

These checks were run against the real app: the Vite dev server, the Flask API and the team's Supabase database. A script drove Microsoft Edge with Playwright, using the `[Demo]` data below. The screenshots are from this run.

| ID | Check | Result | Screenshot |
|----|-------|--------|------------|
| E2E-01 | The nav link opens the list. Each row shows its name, proposed date (as recorded, e.g. `2026-12-12 17:00`) and status, soonest first, with the undated event last. | PASS | [01](SCRUM-62/01-managed-events-list.png) |
| E2E-02 | Another coordinator's event is not in the list. | PASS | [01](SCRUM-62/01-managed-events-list.png) |
| E2E-03 | Opening an event shows its planning information: status, coordinator, all 16 fields, the venue by name and location, and nothing marked "Not recorded". | PASS | [02](SCRUM-62/02-planning-fully-recorded.png) |
| E2E-04 | Unrecorded fields show "Not recorded", none are blank, and registration "No" shows as "No". | PASS | [03](SCRUM-62/03-planning-partly-recorded.png) |
| E2E-05 | An event with no name or date opens and shows "Not recorded". | PASS | [04](SCRUM-62/04-planning-nothing-recorded.png) |
| E2E-06 | A cancelled event still opens. | PASS | — |
| E2E-07 | Another coordinator's event, opened by typing its URL, is refused. No event details and no Retry button are shown. | PASS | [05](SCRUM-62/05-planning-refused.png) |
| E2E-08 | If the API cannot be reached, an error and a Retry button are shown, and Retry loads the list. | PASS | [06](SCRUM-62/06-list-load-failure.png) |
| E2E-09 | A coordinator with no events sees the empty-state message. | PASS | [07](SCRUM-62/07-empty-state.png) |
| E2E-10 | An organiser opening the list is told it is for coordinators. | PASS | [08](SCRUM-62/08-non-coordinator-refused.png) |

**Demo data** (added to Supabase by [scripts/seed_demo_data.py](SCRUM-62/scripts/seed_demo_data.py); every row is marked `[Demo]` or uses an `@connectsphere.demo` email):

- **Accounts** (password `Demo1234!`):
  - `demo.coordinator` has 4 events;
  - `demo.coordinator2` has 1 event;
  - `demo.coordinator3` has none;
  - `demo.organiser`.
- **Events:**
  - a fully recorded festival;
  - a partly recorded approved mixer;
  - a cancelled event;
  - one with a blank name and no date;
  - one belonging to another coordinator.

### d. Limitations and follow-ups

- The end-to-end script and the mutation check are not part of CI. CI runs only the backend tests, and the frontend tests are run by hand (see AGENTS.md).
- The pages are unstyled, like the rest of the app (no CSS framework, per AGENTS.md).
- Q1–Q3 above are assumptions until the customer answers them.

## 4. Evidence documented

- **This document:** [docs/evidence/SCRUM-62-dod-evidence.md](SCRUM-62-dod-evidence.md).
- **Screenshots:** [docs/evidence/SCRUM-62/](SCRUM-62/), files `01`–`08`.
- **Scripts that produced the evidence:** [docs/evidence/SCRUM-62/scripts/](SCRUM-62/scripts/).
  - `mutation_check.py` runs the mutation check (from the repo root, Windows venv path).
  - `e2e_check.mjs` runs the end-to-end check.
  - `seed_demo_data.py` adds the demo data.
- **Test cases and traceability:** [docs/test-cases/SCRUM-62-managed-events-list.md](../test-cases/SCRUM-62-managed-events-list.md).
