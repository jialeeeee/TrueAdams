# SCRUM-96 — Technical Support Views an Event's Equipment Requirements: Definition of Done Evidence

**Story:** As a Technical Support Staff member, I want to view an event's equipment requirements, so that I can record what is arranged as it is arranged.

**Branch:** `feature/SCRUM-96-tech-views-equipment-requirements` (from `main` at `89fe346`) · **Checked:** 29 Oct 2026 · **Test cases:** [SCRUM-96-tech-views-equipment-requirements.md](../test-cases/SCRUM-96-tech-views-equipment-requirements.md) · **Screenshots, scripts and raw results:** [SCRUM-96/](SCRUM-96/)

| # | Definition of Done item | Result |
|---|---|---|
| 1 | Acceptance criteria satisfied | ✅ All 3 ACs met, each shown by automated tests and in the running app ([§1](#1-acceptance-criteria-satisfied)) |
| 2 | All test cases pass | ✅ SCRUM-96 backend 12/12 and frontend 4/4; whole backend suite 1121 run, all pass (4 skipped, none of them SCRUM-96's); whole frontend suite 513/513; end-to-end 5/5 ([§2](#2-all-test-cases-pass)) |
| 3 | Test cases are correct and the code does what it says | ✅ Written test-first (red, then green); 31/31 deliberate breakages caught; behaviour confirmed in a real browser ([§3](#3-test-cases-are-correct-and-the-code-does-what-it-says)) |
| 4 | Evidence of checks documented | ✅ This document, 6 screenshots, the scripts that produced them and the raw results ([§4](#4-evidence-documented)) |

> **Supabase:** no schema change, so there is nothing to run in the SQL editor. Against Supabase on 29 Oct 2026, `python -m unittest tests.test_tech_views_equipment tests.test_equipment_requirements tests.test_app_factory` ran 49 tests: all of SCRUM-96's and SCRUM-42's pass, and one fails that is not this story's. `test_database_tables_match_the_models` finds a column `hold_warned_at` on Supabase's `venue_bookings` that no model or `db/*.sql` script on `main` has, so a script from a branch not yet merged has been run there. It fails the same way on `main` (and CI's `supabase-schema` job) until that branch merges (§3d). The other results below come from a local PostgreSQL 17 built by `ci/build_test_database.py`, as CI's `unittest` job builds it, with the tests logged in as the restricted `connectsphere_test` role.

## What this story changed

Most of this story was already built by SCRUM-42, whose AC4 lets Technical Support Staff view and update an event's equipment requirements (TC-42-19 to 23, 29, 35, 37, 38). SCRUM-96 checks that view from Technical Support's side and closes the one gap it found:

- **Backend:** `GET /api/events/<id>/equipment-requirements` now answers "Event not found." (HTTP 404) for a **draft**, as for an unknown ID. Before, any Technical Support member could open a draft's equipment page and see its title, times and the organiser's private equipment note, although a draft is still the organiser's own (SCRUM-59, SCRUM-74 A2). `_equipment_event` gains a `hide_drafts` option, which only this view passes, so SCRUM-42's other endpoints and SCRUM-43/44's keep their behaviour.
- **Frontend:** no change. Four page tests were added for Technical Support's view.
- **Docs:** the SCRUM-96 test-case document; SCRUM-42's A9 notes the draft rule.

## 1. Acceptance criteria satisfied

| AC | Criterion | How it is met | Automated tests | Seen in the running app |
|----|-----------|---------------|-----------------|-------------------------|
| AC1 | I can open an event's equipment requirements and see the types, quantities and technical requirements. | Technical Support open any event that has left draft, from "Equipment requests" or by its address. Each requirement shows its type, quantity and technical requirements ("None recorded" when blank), in the order recorded, with its arrangement status and note. The page also shows the event and the organiser's note. Cancelled and rejected events are read-only. A draft is "Event not found." | TC-96-01 to 05, 13 · TC-42-19, 20, 35, 38 | E2E-01, 02, 04 · [01](SCRUM-96/01-tech-sees-requirements.png), [02](SCRUM-96/02-arrangement-recorded.png), [04](SCRUM-96/04-draft-not-found.png) |
| AC2 | Only Technical Support Staff can view them. Anyone else is denied and nothing changes. | Technical Support, plus the event's current coordinator, who records them (A2, Q1). Everyone else (other coordinators, the organiser, attendees, Venue Staff, admins, Coordinator Leads, Safety Officers) gets 403 "You are not allowed to view this event's equipment requirements." with no event or requirement details, and no Retry on the page. The role is read from the database on every request. A view never changes a requirement or the event, and sends no notification or email. | TC-96-05 to 09, 14 · TC-42-23, 37 | E2E-03, 04 · [03](SCRUM-96/03-organiser-refused.png) |
| AC3 | If the requirements cannot be loaded, a message explains why and offers a retry. | A failed read of the event or its requirements is 503 `retryable: true`, "The equipment requirements could not be loaded. Please try again.", never an empty list or "not found". The page shows the server's message, or "…Check your connection and try again." when there is no reply, with Retry. Retry loads again on the same page, and the error goes once a load works. | TC-96-10 to 12, 15, 16 · TC-42-29, 37 | E2E-05 · [05](SCRUM-96/05-load-failed.png), [06](SCRUM-96/06-after-retry.png) |

**Working assumptions.** Each is tied to an open question in the test-case document; none has been agreed with the customer:

- **Q1:** AC2 says "only Technical Support Staff"; the event's coordinator also keeps viewing the requirements they record (SCRUM-42 A9). Refusing them would break SCRUM-42.
- **Q2:** Technical Support see every event that has left draft, including submitted and under-review ones; drafts are hidden.
- **Q3:** Technical Support also see the organiser's free-text equipment note.
- **Q4:** "could not be loaded, please try again / check your connection" is taken as explaining why; the database's own error is internal detail and is not shown.

## 2. All test cases pass

| Suite | Command | Result |
|-------|---------|--------|
| Backend, SCRUM-96 | `python -m unittest tests.test_tech_views_equipment` (from `backend/`) | **12/12 pass** (TC-96-01 to 12) |
| Backend, SCRUM-42 to 44 and the safety queue (share the endpoint's helper) | `python -m unittest tests.test_tech_views_equipment tests.test_equipment_requirements tests.test_equipment_availability tests.test_equipment_reservation tests.test_safety_check_queue_local` | **101/101 pass** |
| Backend, whole suite | `python -m unittest discover` | **Ran 1121 tests: OK, 4 skipped.** The skips are SCRUM-36/37 tests waiting on customer answers and a SCRUM-91 test blocked by SCRUM-93. |
| Frontend, SCRUM-96 | `npx vitest run src/pages/EquipmentRequirementsPage.test.jsx` (from `frontend/`) | **4/4 SCRUM-96 tests pass** (TC-96-13 to 16), plus SCRUM-42/43/44's 25 in the same file: 29/29 |
| Frontend, whole suite | `npm test` | **513/513 pass** |
| End-to-end in a real browser | [scripts/e2e_check.mjs](SCRUM-96/scripts/e2e_check.mjs) | **5/5 pass** (§3c), [raw result](SCRUM-96/e2e-results.txt) |

## 3. Test cases are correct and the code does what it says

### a. The test cases match the acceptance criteria

Every AC has API tests and page tests (traceability matrix in the test-case document). The tests were written first and committed as `6eed94e` ("TDD, red"). Only TC-96-05 failed, on the draft: Technical Support got HTTP 200 with the draft's title, times and the organiser's note, and the organiser got 403 instead of 404. The other 11 API tests and the 4 page tests passed straight away, because SCRUM-42 had already built the behaviour; the mutation check (§3b) shows they still catch it when it breaks. One test was corrected before the red commit: TC-96-11 built the event's URL after the simulated outage had started, so the test itself failed reading the event's ID. It now builds the URL first.

### b. The tests catch broken code (mutation check)

Each mutation breaks one rule, runs the tests, and restores the file byte for byte ([mutations](SCRUM-96/scripts/mutations.py), run with SCRUM-77's runner). The backend side ran **only SCRUM-96's tests**, so every catch is theirs.

- **Backend: 20/20 caught** ([results](SCRUM-96/mutation-results-backend.txt)): technical requirements, quantities, the order, the organiser's note or the arrangement note wrong or missing (B1–B5), no arrangement controls (B6), closed events hidden (B7), a draft shown (B8, B9), anyone (B10), any coordinator (B11), Venue Staff (B12) or admins and Leads (B13) let in, a refusal naming the event (B14), a refused view changing the event (B15), a view adding a notification (B16), a deleted user's token treated as 403 (B17), a failed load reported as an empty list (B18), as not retryable (B19) or as "not found" (B20).
- **Frontend: 11/11 caught** ([results](SCRUM-96/mutation-results-frontend.txt)), each by at least one SCRUM-96 test: technical requirements (F1), "None recorded" (F2) or quantities (F3) not shown, the record form shown to Technical Support (F4), Retry offered on a refusal (F5) or missing on a failure (F6), Retry doing nothing (F7), a failure shown as "nothing recorded" (F8), the server's message ignored (F9), no "check your connection" without a reply (F10), the error kept after a Retry that worked (F11).

### c. The running app does what it says (end-to-end)

The real app (Vite → Flask → a local PostgreSQL built by `ci/build_test_database.py`, separate from the test database) driven in Microsoft Edge by [e2e_check.mjs](SCRUM-96/scripts/e2e_check.mjs), on events from [seed_demo_tech_view.py](SCRUM-96/scripts/seed_demo_tech_view.py):

| Check | What | Screenshot |
|---|---|---|
| E2E-01 | Technical Support open the gala from "Equipment requests" and see 2 × Wireless microphone ("Lapel, with spare batteries") and 1 × Projector ("None recorded"), the organiser's note, and no record form (AC1) | [01](SCRUM-96/01-tech-sees-requirements.png) |
| E2E-02 | They mark the microphones Being arranged with a note; reopening the page shows both (AC1, the story's "so that") | [02](SCRUM-96/02-arrangement-recorded.png) |
| E2E-03 | The organiser and another coordinator see only the refusal, with no Retry, title or equipment; the API gives them 403 with only the message; the requirements are unchanged (AC2) | [03](SCRUM-96/03-organiser-refused.png) |
| E2E-04 | A draft's equipment page is "Event not found." for Technical Support, with no Retry, title or note (AC1, AC2) | [04](SCRUM-96/04-draft-not-found.png) |
| E2E-05 | With the request cut off, the page says the requirements could not be loaded and to check the connection, with Retry; once the connection is back, Retry shows both requirements (AC3) | [05](SCRUM-96/05-load-failed.png), [06](SCRUM-96/06-after-retry.png) |

**Runs.** The first run passed 5/5; the screenshots are from it.

### d. Findings for the team (not part of SCRUM-96)

1. **SCRUM-43's availability check and SCRUM-44's reservations page still show a draft's title and times to Technical Support** (`GET /api/events/<draft id>/equipment-availability` and `/equipment-reservations` return 200 with the event; found in the running app). They don't show the organiser's note, and a draft can't have requirements, so nothing else leaks. Passing `hide_drafts=True` in those two routes would close it; it was left out of this story because it changes SCRUM-43/44's behaviour.
2. **AC2's wording conflicts with SCRUM-42** (Q1): taken literally it would stop the coordinator seeing the requirements they record. Built as SCRUM-42 has it; the customer's answer is needed.
3. **Supabase has a column the code doesn't know:** `venue_bookings.hold_warned_at`, presumably from an unmerged venue-hold branch. Until that branch merges, the schema test fails for everyone (see the note at the top).

### e. Limitations

- **The server's 503 was not produced in the browser.** E2E-05 cuts the request off (no reply); the server's own 503 reply and its message are covered by TC-96-10, 11 and 15.
- **The whole suite was run against the local database, as CI does;** against Supabase only SCRUM-96's, SCRUM-42's and the schema tests were run (see the note at the top).
- The demo accounts and events used in the browser check exist only in the local `connectsphere_e2e_96` database.

## 4. Evidence documented

- This document, and the test-case document with its traceability matrix and open questions.
- [SCRUM-96/](SCRUM-96/): screenshots `01`–`06`; `scripts/` (seed script, browser check, mutations); `mutation-results-backend.txt`, `mutation-results-frontend.txt`, `e2e-results.txt`.
- Commits: `6eed94e` (TDD, red), `8c73a77` (TDD, green).
