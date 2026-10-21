# SCRUM-43 — Check Equipment Availability for an Event: Definition of Done Evidence

**Story:** As a Technical Support Staff member, I want to view all available equipment so that I can determine whether an event's equipment requirements can be fulfilled.

**Branch:** `feature/SCRUM-43-equipment-availability` (built on SCRUM-42, PR #47) · **Checked:** 21 Oct 2026 · **Test cases:** [SCRUM-43-equipment-availability.md](../test-cases/SCRUM-43-equipment-availability.md) · **Screenshots, scripts and raw results:** [SCRUM-43/](SCRUM-43/)

| # | Definition of Done item | Result |
|---|---|---|
| 1 | Acceptance criteria satisfied | ✅ All 5 ACs met, each shown by automated tests and in the running app ([§1](#1-acceptance-criteria-satisfied)) |
| 2 | All test cases pass | ✅ SCRUM-43 backend 26/26 and frontend 10/10; whole backend suite: every SCRUM-42/43 test passes (3 unrelated SCRUM-63 failures, §3d); whole frontend suite 386/386; end-to-end 7/7 ([§2](#2-all-test-cases-pass)) |
| 3 | Test cases are correct and the code does what it says | ✅ Written test-first (red, then green); 23/23 deliberate breakages caught; behaviour confirmed in a real browser ([§3](#3-test-cases-are-correct-and-the-code-does-what-it-says)) |
| 4 | Evidence of checks documented | ✅ This document, 3 screenshots, the scripts that produced them and the raw mutation results ([§4](#4-evidence-documented)) |

**Updated 21 Oct 2026:** the stale-result issue the reviewer found in SCRUM-42's PR #47 also applied to this page; it is fixed here too. See [§5](#5-stale-result-fix-carried-over-from-the-review-of-pr-47). Sections 1–4 record the checks as first made.

## What this story changed

- **Database:** a new `equipment_unavailability` table (`backend/db/equipment_unavailability.sql`, run on Supabase on 21 Oct 2026 together with the updated `test_role.sql`): periods when an item of equipment can't be used, with a reason.
- **Backend:** `GET /api/events/<id>/equipment-availability` for Technical Support Staff, and the rules in `backend/app/resources/availability.py`, kept free of Flask and the database so SCRUM-44 can reuse them when it deducts reservations. Unavailable periods are found with the shared `scheduling.overlapping()`.
- **Frontend:** the Equipment availability page (`/events/:id/equipment-availability`), linked from the equipment requirements page for Technical Support Staff.
- **Merge:** the branch was brought up to date with SCRUM-42 and `main` (SCRUM-63, 80, 84) in commit `827f335`. `models.py` and `test_role.sql` conflicted only because SCRUM-63's `venue_changes` table was added at the same places; both were kept.

## 1. Acceptance criteria satisfied

| AC | Criterion | How it is met | Automated tests | Seen in the running app |
|----|-----------|---------------|-----------------|-------------------------|
| AC1 | The check uses the event's equipment types, quantities, technical requirements, and required date and start/end times. | One line per recorded requirement, from the saved data each time, over the event's `[start, end)`. Suitable items are those whose category matches the type (ignoring case and spacing). Technical requirements are shown for Technical Support to confirm. | TC-43-01 to 04, 16, 21; unit rules | E2E-01, 02 · [01](SCRUM-43/01-availability-result.png) |
| AC2 | The result shows the requested quantity and available suitable quantity for each equipment requirement. | Each line shows "Requested: n · Available: m", whether there is enough, and the items counted. Items with no quantity recorded are not counted. A summary says how many requirements can be met. | TC-43-05 to 08, 16; unit rules | E2E-02 · [01](SCRUM-43/01-availability-result.png) |
| AC3 | Equipment recorded as unavailable for the required period is excluded. | An item with an unavailable period overlapping the event is left out and listed as "Not counted" with the period and reason. A period that only touches the event, or is on another day, does not exclude. | TC-43-09 to 11, 17; unit rules | E2E-03 · [01](SCRUM-43/01-availability-result.png) |
| AC4 | Checking availability does not create a reservation. | The check only reads. The page says "Checking availability does not reserve any equipment." Nothing in the result says reserved, booked or confirmed. | TC-43-12, 18; unit rules | E2E-04 (demo stock read from the database: unchanged after two checks) |
| AC5 | Missing timing information or a failed availability check produces an error with details. | Missing times: HTTP 422 naming them (`missing`), shown on the page with no result. A failed check: HTTP 503, retryable, shown as an error with Retry, never as a result. | TC-43-13 to 15, 19, 20 | E2E-05, 06 · [02](SCRUM-43/02-missing-times.png), [03](SCRUM-43/03-check-failed.png) |

**Working assumptions** (each tied to an open question in the test-case document, not agreed with the customer):

- **Q1:** suitable equipment is matched by category.
- **Q2:** technical requirements are shown, not matched automatically.
- **Q3:** an item with no quantity recorded is left out and labelled.
- **Q4:** an unavailable period makes the whole item unavailable.
- **Q5:** nobody can record unavailability in the app yet (no story covers it).
- **Q6:** equipment needs no setup or return time.
- **Q7:** only Technical Support can run the check.

## 2. All test cases pass

| Suite | Command | Result |
|-------|---------|--------|
| Backend, SCRUM-43 through the API | `python -m unittest tests.test_equipment_availability` (from `backend/`) | **15/15 pass** against Supabase (TC-43-01 to 15) |
| Backend, SCRUM-43 rules (no database) | `python -m unittest tests.test_equipment_availability_unit` | **11/11 pass** |
| Backend, whole suite against Supabase, after the merge | `python -m unittest discover` | **Ran 843 tests: 3 failures, 3 skipped.** Every SCRUM-42 and SCRUM-43 test passes. The 3 failures are SCRUM-63's (§3d); the 3 skips are SCRUM-36/37 tests blocked on customer answers. |
| Frontend, SCRUM-43 | `npx vitest run` on the two files below | **10/10 pass**: `EquipmentAvailabilityPage.test.jsx` 8, `EquipmentRequirementsPage.test.jsx` SCRUM-43 link 2 |
| Frontend, whole suite, after the merge | `npm test` (from `frontend/`) | **33 files, 386/386 pass** |
| End-to-end in a real browser | [scripts/e2e_check.mjs](SCRUM-43/scripts/e2e_check.mjs) | **7/7 pass** (§3c) |

## 3. Test cases are correct and the code does what it says

### a. The test cases match the acceptance criteria

- Every AC traces to test cases (traceability matrix in the test-case document), and every automated test names its `TC-43-xx` ID or the assumption it covers.
- The tests were written first. Commit `684840c` ("TDD, red") holds the test-case document and tests only. Against that commit, **none of the 26 backend tests pass** (all error: the model and rules module did not exist), and the frontend tests failed (the page did not exist; the link tests failed). Commit `bd622da` ("TDD, green") made them pass.
- The API tests use the real database and a per-run suffix on every category and type, because the equipment catalogue is shared with real data. They assert exact quantities, which items are counted and which are excluded and why, and that nothing in the database changes when checking.
- Making them pass found one test bug: TC-43-07 meant to create equipment with no quantity recorded, but the model's default (0) replaced `None` on insert, so the test had created a 0. The test now sets NULL after creating the row, and checks the item is excluded as "quantity not recorded".

### b. The tests catch broken code (mutation check)

Each row is a deliberate bug put into the code, one at a time; the SCRUM-43 tests were run against it, then the file was restored byte for byte. After the last one, every test passed again. Runner: [SCRUM-77/scripts/mutation_check.py](SCRUM-77/scripts/mutation_check.py). Mutations: [scripts/mutations.py](SCRUM-43/scripts/mutations.py). Raw output: [backend](SCRUM-43/mutation-results-backend.txt), [frontend](SCRUM-43/mutation-results-frontend.txt).

| ID | Deliberate bug | Should break | Caught? | Failing tests (examples) |
|----|----------------|--------------|---------|--------------------------|
| B1 | Check only the first requirement | AC1 | ✅ | `test_tc_43_01_one_line_per_requirement_for_the_events_period` (+7) |
| B2 | Match categories exactly, so case and spacing matter | AC1 (A2) | ✅ | `test_tc_43_03_types_match_categories_ignoring_case_and_spacing`, `test_types_match_categories_ignoring_case_and_spacing` (+5) |
| B3 | Count only the first suitable item's quantity | AC2 | ✅ | `test_tc_43_05_requested_and_available_quantity_for_each_requirement` (+6) |
| B4 | Exactly the requested quantity is not enough | AC2 | ✅ | `test_tc_43_06_exactly_enough_is_enough`, `test_enough_at_exactly_the_requested_quantity` |
| B5 | Equipment with no quantity recorded is silently left out | AC2 (A4) | ✅ | `test_tc_43_07_equipment_with_no_quantity_recorded_is_not_counted` (+1) |
| B6 | Unavailable equipment is still counted | AC3 | ✅ | `test_tc_43_09_equipment_unavailable_during_the_event_is_excluded` (+6) |
| B7 | Any recorded unavailability excludes, whatever its period | AC1, AC3 | ✅ | `test_tc_43_10_a_period_that_only_touches_the_event_does_not_exclude`, `test_tc_43_11_unavailability_on_another_day_does_not_exclude` (+4) |
| B8 | An exclusion doesn't say why | AC3 | ✅ | `test_tc_43_09_…` (+2) |
| B9 | Checking takes one of each suitable item out of stock | AC4 | ✅ | `test_tc_43_12_checking_changes_nothing_and_reserves_nothing` (+1) |
| B10 | A requirement that can be met is labelled reserved | AC4 | ✅ | `test_tc_43_12_…`, `test_nothing_says_reserved_booked_or_confirmed` (+1) |
| B11 | Missing times are not reported; the check runs anyway | AC5 | ✅ | `test_tc_43_13_missing_times_are_an_error_naming_them` |
| B12 | A failed check is shown as an empty result | AC5 | ✅ | `test_tc_43_14_a_failed_check_is_an_error_not_a_result` |
| B13 | Anyone can run the check | AC5 (A9) | ✅ | `test_tc_43_15_who_may_check_and_in_what_order` |
| B14 | Cancelled and rejected events are checked | AC5 (A10) | ✅ | `test_tc_43_15_…` |
| F1 | Technical Support get no link to the check | AC1 | ✅ | links Technical Support Staff to the availability check |
| F2 | The coordinator is offered the check too | AC1 (A9) | ✅ | does not offer the check to the coordinator |
| F3 | The available quantity is not shown | AC2 | ✅ | shows each requirement with its requested and available quantity |
| F4 | Whether there is enough is not shown | AC2 | ✅ | shows each requirement with its requested and available quantity |
| F5 | The technical requirements note is not shown | AC1 | ✅ | shows each requirement with its requested and available quantity |
| F6 | Excluded equipment is not listed | AC3 | ✅ | lists the equipment excluded and why |
| F7 | The page doesn't say checking reserves nothing | AC4 | ✅ | says that checking does not reserve any equipment |
| F8 | An error is not announced as an alert | AC5 | ✅ | explains missing times without showing a result (+3) |
| F9 | A failed check offers no Retry | AC5 | ✅ | offers Retry after a failed check (+1) |

**Result: 23/23 caught** (backend 14/14, frontend 9/9).

### c. The running app does what it says (end-to-end)

Run against the real app: the Vite dev server, the Flask API and the team's Supabase database. A script drove Microsoft Edge with Playwright as `demo.tech` (Technical Support) and `demo.coordinator`, on fresh events from [scripts/seed_demo_availability.py](SCRUM-43/scripts/seed_demo_availability.py). The demo equipment's categories start with "[Demo]", so real equipment in the shared catalogue cannot change the numbers. The API log for the run has no errors.

Demo data: microphones "[Demo] Shure SLX-D 43" (2) and "[Demo] Sennheiser EW-D 43" (2, category written "[demo]  wireless MICROPHONE"); projectors "[Demo] BenQ LU935" (2) and "[Demo] Epson EB-L" (1, unavailable 5 Dec 2026 17:00–19:00, "Lamp replacement"). The event runs 5 Dec 2026 18:00–23:00 and needs 3 microphones ("Lapel"), 1 projector and 1 hologram projector.

| ID | Check | Result | Screenshot |
|----|-------|--------|------------|
| E2E-01 | From the event's equipment requirements, Technical Support open "Check availability" and see the event, its period and one line per requirement. | PASS | — |
| E2E-02 | Microphones: requested 3, available 4, enough, with "Lapel" to confirm and both microphones counted (one category in different case and spacing). Projector: 1 / 2, enough. Hologram projector: 1 / 0, no suitable equipment. "2 of 3 equipment requirements can be met". | PASS | [01](SCRUM-43/01-availability-result.png) |
| E2E-03 | The Epson is not counted: "Unavailable 2026-12-05 17:00 to 2026-12-05 19:00: Lamp replacement"; the BenQ is. | PASS | [01](SCRUM-43/01-availability-result.png) |
| E2E-04 | The page says checking reserves nothing; "Check again" gives the same result; the demo stock read from the database is the same before and after; nothing says reserved, booked or confirmed. | PASS | — |
| E2E-05 | An event with no times: "The event's start time and end time are not recorded, so equipment availability can't be checked…", no result and no Retry; the API answers 422 with `missing: ["start_time", "end_time"]`. | PASS | [02](SCRUM-43/02-missing-times.png) |
| E2E-06 | With the check cut off before it reaches the server: an error with Retry and no result; Retry then shows the result. | PASS | [03](SCRUM-43/03-check-failed.png) |
| E2E-07 | The coordinator gets HTTP 403 from the check and no "Check availability" link. | PASS | — |

**First run: 6/7.** E2E-06 failed because of the script, not the app: the pattern used to cut off the API call (`**/equipment-availability`) also matched the page's own address, so the page itself was blocked. The script now cuts off only the API address. The second run passed 7/7 on the same events (the check is read-only); the screenshots are from that run.

### d. Findings for the team (not part of SCRUM-43)

1. **Three SCRUM-63 tests assume the `venues` table is empty.** `test_venue_catalogue` (`test_every_other_role_is_refused`, `test_tc2_name_is_required`, `test_tc12_every_invalid_field_is_named_in_one_reply`) assert `Venue.query.count() == 0`. They pass in CI, whose database starts empty, but fail against Supabase, which holds one real venue ("[Demo] Aurora Ballroom", SCRUM-62's demo data). AGENTS.md says tests must not assume a table is empty. Comparing the count before and after the request would fix them. Not changed here: they are SCRUM-63's tests.
2. **Nobody can record equipment unavailability yet.** The table exists, but no screen or endpoint writes it (open question Q5). Until a story adds one, unavailability can only be entered in the database.
3. **"View all available equipment."** The story's wording also suggests a list of all equipment, but `GET /api/resources/` is still a stub returning `[]`. The ACs only need the per-event check, so it was not built here.

### e. Limitations

- The end-to-end script and the mutation check are not part of CI.
- AC5's failed check was shown in the browser by cutting off the request. A database failure itself is covered by TC-43-14 (reads of the catalogue and of unavailability failing in turn).
- The demo data stays in the shared database: four "[Demo]" equipment items, one unavailability period and the `[Demo]` events from each run.

## 4. Evidence documented

- **This document:** [docs/evidence/SCRUM-43-dod-evidence.md](SCRUM-43-dod-evidence.md).
- **Screenshots:** [docs/evidence/SCRUM-43/](SCRUM-43/), files `01`–`03`.
- **Scripts:** [docs/evidence/SCRUM-43/scripts/](SCRUM-43/scripts/):
  - `mutations.py`: the mutations, run with the SCRUM-77 runner;
  - `seed_demo_availability.py`: the demo equipment and events, and the stock read-back used by E2E-04;
  - `e2e_check.mjs`: the end-to-end check.
- **Raw mutation results:** `mutation-results-backend.txt`, `mutation-results-frontend.txt`, `mutation-results-review-frontend.txt`.
- **Test cases and traceability:** [docs/test-cases/SCRUM-43-equipment-availability.md](../test-cases/SCRUM-43-equipment-availability.md).

## 5. Stale-result fix carried over from the review of PR #47

The reviewer of SCRUM-42 found that its equipment page kept the previous event's data when the address changed to another event, and that a late reply for the old event could replace the new one. This page had the same pattern: on a change from `/events/7/equipment-availability` to `/events/8/...`, a slow result for event 7 arriving last would be shown under event 8.

- **Fix:** the page is rendered fresh for each event (keyed by event, as SCRUM-42's page and SCRUM-55's review page), so a result for a page you have left is ignored. Within one event two checks cannot overlap: "Check again" clears the result and is hidden until its check has finished.
- **Tests (TC-43-22):**
  - `shows only the event in the address, even when the previous event's result arrives last`: **fails before the fix, passes after.**
  - `hides Check again while a check is running`: records why one event's checks can't overlap.
  - `EquipmentAvailabilityPage.test.jsx`: 10/10 pass.
- **Mutation:** F10, "pages for different events share their result" (the key removed), is **caught** ([raw output](SCRUM-43/mutation-results-review-frontend.txt), [scripts/mutations_review.py](SCRUM-43/scripts/mutations_review.py)). All 24 SCRUM-43 mutation patterns still match the code after the merge.
- **The branch now includes the merged SCRUM-42**, review fixes included (commit `58cceba`). Every SCRUM-42 and SCRUM-43 backend test passes on it: 78/78 with the schema check and the SCRUM-27 route walk.
- **Not repeated:** the end-to-end check in §3c. The fix only changes what happens when the page moves between events, which the demo run does not do.
