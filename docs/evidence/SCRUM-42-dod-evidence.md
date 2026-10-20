# SCRUM-42 — Record Equipment Requirements for an Event: Definition of Done Evidence

**Story:** As an Event Coordinator, I want to record an event's equipment requirements so that Technical Support Staff can assess what needs to be arranged.

**Branch:** `feature/SCRUM-42-equipment-requirements` (PR #47) · **Checked:** 21 Oct 2026 · **Test cases:** [SCRUM-42-equipment-requirements.md](../test-cases/SCRUM-42-equipment-requirements.md) · **Screenshots, scripts and raw results:** [SCRUM-42/](SCRUM-42/)

| # | Definition of Done item | Result |
|---|---|---|
| 1 | Acceptance criteria satisfied | ✅ All 7 ACs met, each shown by automated tests and in the running app ([§1](#1-acceptance-criteria-satisfied)) |
| 2 | All test cases pass | ✅ SCRUM-42 backend 29/29 and frontend 19/19; whole backend suite green in CI on PR #47; whole frontend suite 356/356; end-to-end 13/13 ([§2](#2-all-test-cases-pass)) |
| 3 | Test cases are correct and the code does what it says | ✅ Written test-first (red, then green); 29/29 deliberate breakages caught; behaviour confirmed in a real browser ([§3](#3-test-cases-are-correct-and-the-code-does-what-it-says)) |
| 4 | Evidence of checks documented | ✅ This document, 8 screenshots, the scripts that produced them and the raw mutation results ([§4](#4-evidence-documented)) |

## What this story changed

- **Database:** a new `equipment_requirements` table (`backend/db/equipment_requirements.sql`, run on Supabase on 21 Oct 2026 together with the updated `test_role.sql`). One row per item: type, quantity, technical requirements, arrangement status and note, and who recorded or updated it and when. The organiser's free-text `events.equipment_requirements` (SCRUM-29) is unchanged.
- **Backend:** six routes under `/api/events` (view, record, edit, remove, update the arrangement, list equipment requests) and the validation rules in `backend/app/events/equipment.py`.
- **Frontend:** the Equipment requirements page (`/events/:id/equipment`, linked from the planning page) and the Equipment requests page for Technical Support (`/equipment-requests`, in the navigation).
- **Another story's test:** SCRUM-27's `test_invalid_tokens_never_reach_the_user_lookup` filled in only `<int:event_id>` when building each route's URL. It now fills in every `<int:...>` parameter (§3d).

## 1. Acceptance criteria satisfied

| AC | Criterion | How it is met | Automated tests | Seen in the running app |
|----|-----------|---------------|-----------------|-------------------------|
| AC1 | The coordinator can select an event they are authorised to coordinate and enter equipment types, quantities, and relevant technical requirements. | Only the event's assigned coordinator can record, edit or remove (everyone else gets 403). Reached from the event's planning page. Cancelled and rejected events are read-only (409). | TC-42-01 to 08, 30, 31, 34, 36, 39 | E2E-01, 03, 06, 07, 12 · [01](SCRUM-42/01-nothing-recorded-yet.png), [03](SCRUM-42/03-requirements-recorded.png), [07](SCRUM-42/07-cancelled-read-only.png) |
| AC2 | Invalid equipment requirements are identified and are not saved until corrected. | Type (1–100 characters), quantity (whole number 1–1,000) and technical requirements (up to 1,000 characters) are checked before anything is saved; every invalid field is named next to it (422), and the entry stays on the page. The same requirement can't be recorded twice. | TC-42-09 to 15, 32 | E2E-02, 04 · [02](SCRUM-42/02-invalid-entry.png) |
| AC3 | Successful saving records the requirements against the selected event, and the saved requirements can subsequently be viewed. | Each requirement is stored against its event and listed in the order recorded, with a confirmation. Other events' requirements never appear. | TC-42-01, 03, 05, 12, 16, 17, 18, 30, 31 | E2E-03, 05 · [03](SCRUM-42/03-requirements-recorded.png) |
| AC4 | Technical Support Staff can view the requirements and update the request as arrangements are made. | `tech_staff` see open events with requirements (Equipment requests) and set each requirement's status (Requested, Being arranged, Suitable equipment unavailable) with a note; the coordinator sees who updated it and when. Nobody else can update arrangements. | TC-42-06, 19 to 23, 28, 35, 38 | E2E-07 to 10 · [04](SCRUM-42/04-equipment-requests.png), [05](SCRUM-42/05-arrangements-updated.png), [06](SCRUM-42/06-coordinator-sees-arrangements.png) |
| AC5 | Recording an equipment requirement does not itself reserve equipment or reduce the quantity considered available. | Recording, editing and updating touch only `equipment_requirements`. The confirmation says recording does not reserve any equipment. | TC-42-24, 31 | E2E-03, 11 (demo equipment: 4 available before and after, read from the database) |
| AC6 | A requirement can remain recorded even when suitable equipment is unavailable; it is not represented as fulfilled or reserved. | A type with no matching equipment can be recorded. "Suitable equipment unavailable" keeps it recorded. No status, label or option says reserved or fulfilled (reserving is SCRUM-44). | TC-42-22, 25, 26, 35 | E2E-03, 09, 10 · [05](SCRUM-42/05-arrangements-updated.png), [06](SCRUM-42/06-coordinator-sees-arrangements.png) |
| AC7 | If saving fails, existing recorded requirements remain unchanged and the Event Coordinator is informed. | A failed save, edit, removal or status update is rolled back and answered with a retryable 503 saying the recorded requirements are unchanged; the page shows it and keeps the entry. A failed load is an error, never an empty list. | TC-42-14, 27, 28, 29, 33, 37, 38 | E2E-13 · [08](SCRUM-42/08-save-failed.png) |

**Working assumptions** (each tied to an open question in the test-case document, not agreed with the customer):

- **Q1:** only the event's *assigned* coordinator records requirements.
- **Q2:** cancelled and rejected events are locked; every other status can be edited.
- **Q3:** at most 1,000 of one item per requirement.
- **Q4:** equipment types are free text, not a fixed list.
- **Q5:** the organiser's free-text note is kept alongside the recorded requirements.
- **Q6:** Technical Support "update the request" with a status and a note.
- **Q7:** editing a requirement's details sends it back to Requested.
- **Q8:** the organiser and the Coordinator Lead can't view the requirements.
- **Q9:** no notifications are sent.

## 2. All test cases pass

| Suite | Command | Result |
|-------|---------|--------|
| Backend, SCRUM-42 | `python -m unittest tests.test_equipment_requirements` (from `backend/`) | **29/29 pass** (TC-42-01 to 29), against Supabase |
| Backend, whole suite against Supabase | `python -m unittest discover` | **Ran 760 tests: 4 failures, 3 skipped** (21 Oct 2026). All 4 failures were one SCRUM-27 test (§3d), fixed and re-run: `tests.test_authorization_http_unit` 15/15 pass. The 3 skips are SCRUM-36/37 tests blocked on customer answers. |
| Backend, whole suite in CI (what merges are checked on) | GitHub Actions on PR #47 | **`unittest` pass** (whole suite on a throwaway PostgreSQL, after the fix) and **`supabase-schema` pass** (Supabase matches the models) |
| Frontend, SCRUM-42 | `npx vitest run` on the three files below | **19/19 pass**: `EquipmentRequirementsPage.test.jsx` 14, `EquipmentRequestsPage.test.jsx` 4, `EventPlanningPage.test.jsx` link 1 |
| Frontend, whole suite | `npm test` (from `frontend/`) | **30 files, 356/356 pass** |
| End-to-end in a real browser | [scripts/e2e_check.mjs](SCRUM-42/scripts/e2e_check.mjs) | **13/13 pass** on the first run (§3c) |

## 3. Test cases are correct and the code does what it says

### a. The test cases match the acceptance criteria

- Every AC traces to test cases (traceability matrix in the test-case document), and every automated test names its `TC-42-xx` ID.
- The tests were written first. Commit `0da6d48` ("TDD, red") holds the test-case document and tests only: against that commit, **all 29 backend tests failed** (no `... ok` in the verbose run) and the frontend test files failed to load because the pages did not exist. Commit `866f19f` ("TDD, green") made them pass.
- The tests assert exact outcomes against the real database: what is stored for the event (not just the HTTP status), that nothing is saved after a refusal, that a refusal contains no event details, and that the demo equipment's `quantity_available` is unchanged.
- Making them pass found two real problems, both fixed before the green commit:
  - **The confirmation was overwritten.** Success replies put the confirmation in `message`, which the page payload also uses for the empty-list text, so the confirmation was replaced by `null`. Success replies now use `confirmation`.
  - **The browser blocked invalid saves.** The quantity field's `min="1"` made the browser refuse to submit, so the server's field-by-field messages never appeared. The form now uses `noValidate`.
- One test was itself wrong: TC-42-29 simulated an outage on any SQL mentioning `equipment_requirements`, which also matched the `events` column of that name, so it failed while building its own URL. It now fails only reads of the table.

### b. The tests catch broken code (mutation check)

Each row is a deliberate bug put into the code, one at a time; the SCRUM-42 tests were run against it, then the file was restored byte for byte. After the last one, every test passed again. Runner: [SCRUM-77/scripts/mutation_check.py](SCRUM-77/scripts/mutation_check.py). Mutations: [scripts/mutations.py](SCRUM-42/scripts/mutations.py). Raw output: [backend](SCRUM-42/mutation-results-backend.txt), [frontend](SCRUM-42/mutation-results-frontend.txt).

| ID | Deliberate bug | Should break | Caught? | Failing tests (examples) |
|----|----------------|--------------|---------|--------------------------|
| B1 | Let any coordinator record, not only the event's | AC1 | ✅ | `test_tc_42_04_only_the_events_coordinator_can_record_edit_or_remove` |
| B2 | Record requirements for cancelled and rejected events | AC1 | ✅ | `test_tc_42_07_cancelled_and_rejected_events_cannot_be_changed` |
| B3 | Accept a blank equipment type | AC2 | ✅ | `test_tc_42_09_…`, `test_tc_42_12_…` |
| B4 | Accept a quantity of 0 or above the maximum | AC2 | ✅ | `test_tc_42_10_quantity_must_be_a_whole_number_from_1_to_1000` (+1) |
| B5 | Allow the same requirement to be recorded twice | AC2 | ✅ | `test_tc_42_13_the_same_requirement_cannot_be_recorded_twice` |
| B6 | Name only the first invalid field | AC2 | ✅ | `test_tc_42_12_every_problem_is_named_and_the_corrected_entry_saves` |
| B7 | Show other events' requirements with this event's | AC3 | ✅ | `test_tc_42_16_saved_requirements_are_shown_against_the_event` |
| B8 | Leave out the organiser's equipment note | AC3 | ✅ | `test_tc_42_16_…` |
| B9 | Technical Support Staff can't view requirements | AC4 | ✅ | `test_tc_42_19_technical_support_can_view_any_events_requirements` (+1) |
| B10 | Anyone can update an arrangement | AC4 | ✅ | `test_tc_42_23_only_technical_support_update_and_others_cannot_view` |
| B11 | An arrangement update isn't saved | AC4 | ✅ | `test_tc_42_21_technical_support_update_the_arrangement` (+3) |
| B12 | Editing the details keeps the old arrangement status | AC4 (A8) | ✅ | `test_tc_42_06_editing_the_details_sends_it_back_to_requested` |
| B13 | Technical Support can mark a requirement reserved | AC4, AC6 | ✅ | `test_tc_42_22_only_valid_arrangement_statuses_are_accepted` (+1) |
| B14 | Recording reduces the equipment's available quantity | AC5 | ✅ | `test_tc_42_24_recording_does_not_reserve_or_reduce_availability` |
| B15 | A recorded requirement is shown as reserved | AC5, AC6 | ✅ | `test_tc_42_24_…`, `test_tc_42_25_…` (+11) |
| B16 | Marking a requirement unavailable removes it | AC6 | ✅ | `test_tc_42_26_unavailable_stays_recorded_and_is_not_fulfilled` |
| B17 | A failed save is not rolled back | AC7 | ✅ | `test_tc_42_27_a_failed_save_keeps_existing_requirements` |
| B18 | A failed load is shown as an empty list | AC7 | ✅ | `test_tc_42_29_a_failed_load_is_a_failure_not_an_empty_list` |
| F1 | The planning page has no Equipment requirements link | AC1 | ✅ | links to the equipment requirements |
| F2 | Cancelled and rejected events still show the record form | AC1 | ✅ | shows a cancelled event's requirements read-only (+1) |
| F3 | Invalid fields are not named next to the field | AC2 | ✅ | shows each invalid field and keeps what was entered |
| F4 | What was entered is cleared when a save fails | AC2, AC7 | ✅ | keeps the entry when saving fails so it can be saved again (+1) |
| F5 | The quantity is sent as text | AC1 | ✅ | records a requirement and shows the confirmation (+1) |
| F6 | The recorded requirements are not listed | AC3 | ✅ | shows the event, the organiser's note and the recorded requirements (+8) |
| F7 | The confirmation is not shown | AC3, AC5 | ✅ | records a requirement and shows the confirmation (+4) |
| F8 | Technical Support Staff get no status controls | AC4 | ✅ | lets Technical Support Staff update the arrangement status (+1) |
| F9 | Technical Support are offered a Reserved status | AC4, AC6 | ✅ | lets Technical Support Staff update the arrangement status |
| F10 | Equipment requests link to the planning page instead | AC4 | ✅ | lists each event with its coordinator and arrangement progress, linking to its requirements |
| F11 | A failed load offers no Retry | AC7 | ✅ | offers Retry after a load failure |

**Result: 29/29 caught** (backend 18/18, frontend 11/11). Each failure came from a test's own assertion, not from code that no longer compiled.

### c. The running app does what it says (end-to-end)

Run against the real app: the Vite dev server, the Flask API and the team's Supabase database. A script drove Microsoft Edge with Playwright as `demo.coordinator` and the new Technical Support demo account `demo.tech`, on fresh events from [scripts/seed_demo_equipment.py](SCRUM-42/scripts/seed_demo_equipment.py). No Redis was needed: SCRUM-42 sends no emails. The API log for the run has no errors.

| ID | Check | Result | Screenshot |
|----|-------|--------|------------|
| E2E-01 | From the event's planning page, the coordinator opens Equipment requirements and sees the event, the organiser's note and "No equipment requirements have been recorded". | PASS | [01](SCRUM-42/01-nothing-recorded-yet.png) |
| E2E-02 | A blank type and quantity 0 name both problems next to their fields; what was entered stays, and nothing is listed. | PASS | [02](SCRUM-42/02-invalid-entry.png) |
| E2E-03 | Recording 2 × Wireless microphone ("Lapel, with spare batteries") confirms that recording does not reserve any equipment. 1 × Hologram projector (no such equipment exists) is recorded too. Both show Requested. | PASS | [03](SCRUM-42/03-requirements-recorded.png) |
| E2E-04 | "wireless MICROPHONE" with "lapel,  with spare batteries" is refused as already recorded ("Change its quantity instead"). | PASS | — |
| E2E-05 | After reloading, both requirements are still listed. | PASS | — |
| E2E-06 | Editing the microphones to 3 shows "Updated 3 × Wireless microphone"; a Projector is recorded and removed again. | PASS | — |
| E2E-07 | Through the API: another coordinator and Technical Support can't record (403), the organiser can't view (403), and a coordinator can't open the equipment requests list (403). | PASS | — |
| E2E-08 | Technical Support see the event on Equipment requests: "2 requirements — Requested: 2 · Being arranged: 0 · Suitable equipment unavailable: 0". The cancelled event is not listed. | PASS | [04](SCRUM-42/04-equipment-requests.png) |
| E2E-09 | Technical Support get exactly three statuses and no record form; they set the microphones to Being arranged with a note and the projector to Suitable equipment unavailable. | PASS | [05](SCRUM-42/05-arrangements-updated.png) |
| E2E-10 | The coordinator sees both statuses and the note; the projector stays listed; nothing on the page says reserved or fulfilled. | PASS | [06](SCRUM-42/06-coordinator-sees-arrangements.png) |
| E2E-11 | Read straight from the database: the requirements are as shown, and "[Demo] Shure SLX-D" (category Wireless microphone) still has **4 available**, as before. | PASS | — |
| E2E-12 | A cancelled event's requirements are shown with "This event is cancelled, so its equipment requirements can no longer be changed.", no form or Edit buttons; the API refuses a new one (409). | PASS | [07](SCRUM-42/07-cancelled-read-only.png) |
| E2E-13 | With the save cut off before it reaches the server, the page says the requirement was not saved and the recorded requirements are unchanged, and keeps "Speaker", 2. After reloading, still exactly two requirements, in the page and in the database. | PASS | [08](SCRUM-42/08-save-failed.png) |

### d. Findings for the team (not part of SCRUM-42's ACs)

1. **SCRUM-27's invalid-token test only handled `<int:event_id>`.** It walks every protected route, but replaced only `<int:event_id>` in the URL, so the first routes with a second ID (`<int:requirement_id>`) were requested with that text literally in the path and got 404 instead of 401/422. It now fills in every `<int:...>` parameter. It passes on `main`'s code and on this branch. Please check, @RealStuff29.
2. **Technical Support Staff have no home page after login.** SCRUM-75's `ROLE_HOME_PATHS` (`frontend/src/pages/LoginPage.jsx`) has no entry for `tech_staff`, so they land on the public Events page. Adding `tech_staff: "/equipment-requests"` would take them straight to their work. Not changed here, because it is SCRUM-75's behaviour.

### e. Limitations

- The end-to-end script and the mutation check are not part of CI.
- The whole backend suite was run against Supabase before the one-line SCRUM-27 test fix; after it, that file was re-run locally and the whole suite ran in CI on PR #47.
- AC7 in the browser was shown with the save cut off in the network. A database failure itself is covered by TC-42-27 to 29 (commit failure and outage simulated in the backend tests).
- Two identical requirements saved at the same instant could both be accepted: duplicates are checked in the application, not by a database constraint.
- The demo data stays in the shared database: the `demo.tech@connectsphere.demo` account (password `Demo1234!`), "[Demo] Shure SLX-D" and the `[Demo]` events from each run.

## 4. Evidence documented

- **This document:** [docs/evidence/SCRUM-42-dod-evidence.md](SCRUM-42-dod-evidence.md).
- **Screenshots:** [docs/evidence/SCRUM-42/](SCRUM-42/), files `01`–`08`.
- **Scripts:** [docs/evidence/SCRUM-42/scripts/](SCRUM-42/scripts/):
  - `mutations.py`: the mutations, run with the SCRUM-77 runner;
  - `seed_demo_equipment.py`: the demo account, equipment and events, and the database read-back used by E2E-11;
  - `e2e_check.mjs`: the end-to-end check.
- **Raw mutation results:** `mutation-results-backend.txt`, `mutation-results-frontend.txt`.
- **Test cases and traceability:** [docs/test-cases/SCRUM-42-equipment-requirements.md](../test-cases/SCRUM-42-equipment-requirements.md).
