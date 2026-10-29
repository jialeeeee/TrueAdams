# SCRUM-97 — Technical Support Updates an Event's Equipment Requirements: Definition of Done Evidence

**Story:** As a Technical Support Staff member, I want to update an event's equipment requirements as arrangements are made, so that the record shows what has been arranged.

**Branch:** `feature/SCRUM-97-tech-updates-equipment-requirements` (from `main` at `76cc692`) · **Checked:** 30 Oct 2026 · **Test cases:** [SCRUM-97-tech-updates-equipment-requirements.md](../test-cases/SCRUM-97-tech-updates-equipment-requirements.md) · **Screenshots, scripts and raw results:** [SCRUM-97/](SCRUM-97/)

| # | Definition of Done item | Result |
|---|---|---|
| 1 | Acceptance criteria satisfied | ✅ All 3 ACs met, each shown by automated tests and in the running app ([§1](#1-acceptance-criteria-satisfied)) |
| 2 | All test cases pass | ✅ SCRUM-97 backend 13/13 and frontend 6/6; whole backend suite 1177 run, all pass (4 skipped, none of them SCRUM-97's); whole frontend suite 529/529; end-to-end 5/5 ([§2](#2-all-test-cases-pass)) |
| 3 | Test cases are correct and the code does what it says | ✅ Written test-first (red, then green); 27/27 deliberate breakages caught; behaviour confirmed in a real browser ([§3](#3-test-cases-are-correct-and-the-code-does-what-it-says)) |
| 4 | Evidence of checks documented | ✅ This document, 6 screenshots, the scripts that produced them and the raw results ([§4](#4-evidence-documented)) |

> **Supabase:** no schema change, so there is nothing to run in the SQL editor. Against Supabase on 30 Oct 2026, `python -m unittest tests.test_tech_updates_equipment tests.test_tech_views_equipment tests.test_equipment_requirements tests.test_app_factory` ran 62 tests, all passing, including the schema check (the `hold_warned_at` mismatch found in SCRUM-96 is gone now that SCRUM-86 has merged). The other results below come from a local PostgreSQL 17 built by `ci/build_test_database.py`, as CI's `unittest` job builds it, with the tests logged in as the restricted `connectsphere_test` role.

## What this story changed

SCRUM-42 (AC4) already let Technical Support set each requirement's arrangement status and note, and stored who did it and when. SCRUM-97 checks that from Technical Support's side and closes four gaps:

- **Who and when are shown** (AC1): the page now shows "Arrangement updated by <email> on <date and time>" under each requirement that has been updated. Before, they were saved but never shown.
- **An update that changes nothing keeps who and when** (AC1): it used to replace them, so pressing Update again made someone look responsible for an arrangement they hadn't touched. It now says "No changes were made to the arrangement for 2 × Wireless microphone."
- **An update is for the details Technical Support saw** (AC1, AC2): the page sends the requirement's `last_saved_at`. If the coordinator changed the requirement since (which sends it back to Requested, SCRUM-42 A8), the update is refused with 409 and nothing changes, and the page reloads to show the new details. The row is locked (`SELECT … FOR UPDATE`) while it is checked and saved, as the coordinator's edit already locks it. Before, a note written for 2 microphones could be saved against 5.
- **A failed save says the requirements are unchanged** (AC3): "The arrangement was not saved, and the recorded requirements are unchanged. Please try again." (was "The arrangement status was not saved. Please try again.").
- **Drafts:** updating a draft's requirement is now "Event not found." (404), as viewing is since SCRUM-96. Before, Technical Support could update one (a draft can only have a requirement if it is inserted directly) and the reply included the draft's title and the organiser's note.

Code: `update_equipment_arrangement` in `backend/app/events/routes.py` and `EquipmentRequirementsPage.jsx`. SCRUM-42's test-case document (A7) and test docstring note the change; its TC-42-35 page test now expects `last_saved_at` in the update.

## 1. Acceptance criteria satisfied

| AC | Criterion | How it is met | Automated tests | Seen in the running app |
|----|-----------|---------------|-----------------|-------------------------|
| AC1 | I can update a requirement as arrangements are made, and the update is saved with who and when. | Technical Support set the status (Requested, Being arranged, Suitable equipment unavailable) and a note. The update is saved with who made it and when (UTC), replacing the last, and the page shows both. An update that changes nothing keeps the earlier who and when. An update for details the coordinator has since changed is refused, and the page shows the new details. The coordinator's details can't be changed this way. | TC-97-01 to 06, 14, 15, 19 · TC-42-21, 22, 35 | E2E-01, 02, 04 · [01](SCRUM-97/01-update-saved-with-who-and-when.png), [02](SCRUM-97/02-unchanged-update-keeps-who-and-when.png), [04](SCRUM-97/04-changed-details-refused.png) |
| AC2 | Only Technical Support Staff can update. Anyone else is denied and nothing changes. | Everyone else, including the event's own coordinator, gets 403 "Only Technical Support Staff can update equipment arrangements." with no event or requirement details. The role is read from the database on every request. A refusal changes no requirement, the event or its notifications, and sends no email. A draft is "Event not found." for everyone. | TC-97-05 to 10, 16 · TC-42-23 | E2E-03 · [03](SCRUM-97/03-coordinator-sees-but-cannot-update.png) |
| AC3 | If saving fails, the existing requirements are unchanged and an error is shown. | A failed read or save is 503 `retryable: true`, "The arrangement was not saved, and the recorded requirements are unchanged. Please try again.", never "not found", and every requirement stays as it was. The page shows that (or "…Check your connection and try again." with no reply), keeps the requirements as they were and what was chosen and typed, so Update tries again. | TC-97-11 to 13, 17, 18 · TC-42-28 | E2E-05 · [05](SCRUM-97/05-save-failed.png), [06](SCRUM-97/06-saved-on-trying-again.png) |

**Working assumptions.** Each is tied to an open question in the test-case document; none has been agreed with the customer:

- **Q1:** "Updating a requirement" is setting its arrangement status and a note. Technical Support don't change the type, quantity or technical requirements, and nothing here reserves equipment (SCRUM-44).
- **Q2:** Only the latest update, with who and when, is kept, not a history; an update that changes nothing records nothing.
- **Q3:** An update for details the coordinator has since changed is refused so Technical Support check the new details.
- **Q4:** "Not saved, the recorded requirements are unchanged, please try again" explains a failed save.

## 2. All test cases pass

| Suite | Command | Result |
|-------|---------|--------|
| Backend, SCRUM-97 | `python -m unittest tests.test_tech_updates_equipment` (from `backend/`) | **13/13 pass** (TC-97-01 to 13) |
| Backend, the equipment stories | `python -m unittest tests.test_tech_updates_equipment tests.test_tech_views_equipment tests.test_equipment_requirements tests.test_equipment_availability tests.test_equipment_reservation` | **113/113 pass** |
| Backend, whole suite | `python -m unittest discover` | **Ran 1177 tests: OK, 4 skipped** (on the green commit). The skips are SCRUM-36/37 tests waiting on customer answers and a SCRUM-91 test blocked by SCRUM-93. |
| Frontend, SCRUM-97 | `npx vitest run src/pages/EquipmentRequirementsPage.test.jsx` (from `frontend/`) | **6/6 SCRUM-97 tests pass** (TC-97-14 to 19), plus SCRUM-42/43/44/96's 29 in the same file: 35/35 |
| Frontend, whole suite | `npm test` | **529/529 pass** |
| End-to-end in a real browser | [scripts/e2e_check.mjs](SCRUM-97/scripts/e2e_check.mjs) | **5/5 pass** (§3c), [raw result](SCRUM-97/e2e-results.txt) |

## 3. Test cases are correct and the code does what it says

### a. The test cases match the acceptance criteria

Every AC has API tests and page tests (traceability matrix in the test-case document). The tests were written first and committed as `41ed2f6` ("TDD, red"):

- **Backend:** 6 of 13 failed: an unchanged update replaced who and when (TC-97-04), an update for changed details was saved (05), a draft's requirement could be updated and the reply showed its title and note (10), and the failure message didn't say the requirements were unchanged (11–13). The other 7 passed straight away, because SCRUM-42 had already built them; the mutation check (§3b) shows they still catch it when it breaks.
- **Frontend:** 6 failed: who and when weren't shown (TC-97-14 to 16), the update didn't send `last_saved_at` (14 and SCRUM-42's TC-42-35), the no-reply message (18) and the reload after a change (19). TC-97-17 passed, because the page already kept the entry after a failed save.

Two checks were added to TC-97-05 with the implementation (`6c042d6`): the requirement is read with `SELECT … FOR UPDATE` before it is saved, and an update without `last_saved_at` (an older page) is still accepted. Without them the mutation check would have missed removing the lock or refusing older pages.

### b. The tests catch broken code (mutation check)

Each mutation breaks one rule, runs the tests, and restores the file byte for byte ([mutations](SCRUM-97/scripts/mutations.py), run with SCRUM-77's runner). The backend side ran **only SCRUM-97's tests**, so every catch is theirs.

- **Backend: 18/18 caught** ([results](SCRUM-97/mutation-results-backend.txt)): the update recorded as the coordinator's (B1) or at the wrong time (B2); the status (B3) or note (B4) not saved; an unchanged update replacing who and when (B5) or a note-only change ignored (B6); an update for changed details saved (B7), an older page refused (B8), no reload asked for (B9), no lock (B10); a draft updatable (B11); anyone (B12) or the coordinator (B13) allowed; a refusal naming the event (B14); the requirement looked up before the permission check (B15); a failed save not saying the requirements are unchanged (B16), not retryable (B17) or reported as "not found" (B18).
- **Frontend: 9/9 caught** ([results](SCRUM-97/mutation-results-frontend.txt)): who and when not shown (F1), the time shown as raw UTC (F2), the wrong person named (F3), `last_saved_at` not sent (F4), no reload after a change (F5), the requirement shown as updated before the server agreed (F6), no error shown (F7), the server's message ignored (F8), the old no-reply message (F9).

### c. The running app does what it says (end-to-end)

The real app (Vite → Flask → a local PostgreSQL `connectsphere_e2e_97` built by `ci/build_test_database.py`, separate from the test database) driven in Microsoft Edge by [e2e_check.mjs](SCRUM-97/scripts/e2e_check.mjs), on an event from [seed_demo_tech_update.py](SCRUM-97/scripts/seed_demo_tech_update.py):

| Check | What | Screenshot |
|---|---|---|
| E2E-01 | demo.tech marks the microphones Being arranged with a note; after a reload the page shows the status, the note and "Arrangement updated by demo.tech@… on …", and the API has the same (AC1) | [01](SCRUM-97/01-update-saved-with-who-and-when.png) |
| E2E-02 | demo.tech2 marks them unavailable, and is shown as the updater; demo.tech then presses Update without changing anything: "No changes were made…", demo.tech2 is still shown, and the stored requirement is identical (AC1) | [02](SCRUM-97/02-unchanged-update-keeps-who-and-when.png) |
| E2E-03 | The coordinator sees who and when but has no arrangement controls; the coordinator's and organiser's updates through the API get 403 with only the message, and the requirements are unchanged (AC2) | [03](SCRUM-97/03-coordinator-sees-but-cannot-update.png) |
| E2E-04 | With demo.tech's page open, the coordinator changes the microphones to 5; demo.tech's update is refused with the message naming 5 × Wireless microphone, the page shows 5 × Wireless microphone at Requested without the typed note, and updating it again works (AC1) | [04](SCRUM-97/04-changed-details-refused.png) |
| E2E-05 | With the update cut off, the page says the arrangement was not saved and the requirements are unchanged, the projector is still Requested (also in the API), and the choice and note stay; once the connection is back, Update saves it (AC3) | [05](SCRUM-97/05-save-failed.png), [06](SCRUM-97/06-saved-on-trying-again.png) |

**Runs.** The first run passed 4/5: E2E-04's script looked for the text "5 × Wireless microphone", which also appears inside the refusal message, so the locator matched two elements. The script now matches the requirement's name exactly. A second run on a freshly seeded event passed 5/5; the screenshots are from it.

### d. Findings for the team (not part of SCRUM-97)

- Two Technical Support members updating the same requirement at once: the later update wins, and its who and when are shown (A5). Only a change by the coordinator is refused.
- Still open from SCRUM-96: SCRUM-43's availability check and SCRUM-44's reservations page show a draft's title and times to Technical Support.

### e. Limitations

- **The server's 503 was not produced in the browser.** E2E-05 cuts the request off (no reply); the server's own 503 and its message are covered by TC-97-11 to 13 and 17.
- **The lock is checked by the SQL it sends, not by two real concurrent requests.** The tests run in one transaction, so TC-97-05 checks that the requirement is read with `SELECT … FOR UPDATE` before it is saved.
- **Against Supabase only the equipment stories' and the schema tests were run** (see the note at the top); the whole suite was run against the local database, as CI does.
- The demo accounts and event used in the browser check exist only in the local `connectsphere_e2e_97` database.

## 4. Evidence documented

- This document, and the test-case document with its traceability matrix and open questions.
- [SCRUM-97/](SCRUM-97/): screenshots `01`–`06`; `scripts/` (seed script, browser check, mutations); `mutation-results-backend.txt`, `mutation-results-frontend.txt`, `e2e-results.txt`.
- Commits: `41ed2f6` (TDD, red), `6c042d6` (TDD, green).
