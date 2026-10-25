# SCRUM-44 — Reserve Equipment for an Event: Definition of Done Evidence

**Story:** As a Technical Support Staff member, I want to reserve available equipment for an event so that its equipment needs are secured without overallocation of equipment.

**Branch:** `feature/SCRUM-44-reserve-equipment` (from `main` at `f77f4b0`, which already has SCRUM-42 and SCRUM-43) · **Checked:** 23 Oct 2026 · **Test cases:** [SCRUM-44-reserve-equipment.md](../test-cases/SCRUM-44-reserve-equipment.md) · **Screenshots, scripts and raw results:** [SCRUM-44/](SCRUM-44/)

| # | Definition of Done item | Result |
|---|---|---|
| 1 | Acceptance criteria satisfied | ✅ All 9 ACs met, each shown by automated tests and in the running app ([§1](#1-acceptance-criteria-satisfied)) |
| 2 | All test cases pass | ✅ After the review fixes ([§5](#5-review-fixes-25-oct-2026)): SCRUM-44 backend 56/56 and frontend 25/25; whole frontend suite 448/449, and the 1 failure is SCRUM-84's and fails on `main` too (§3d). Before them: whole backend suite 927 pass (3 skipped, not SCRUM-44's); end-to-end 9/9 ([§2](#2-all-test-cases-pass)) |
| 3 | Test cases are correct and the code does what it says | ✅ Written test-first (red, then green); 48/48 deliberate breakages caught; behaviour confirmed in a real browser ([§3](#3-test-cases-are-correct-and-the-code-does-what-it-says)) |
| 4 | Evidence of checks documented | ✅ This document, 8 screenshots, the scripts that produced them and the raw results ([§4](#4-evidence-documented)) |

> **Before merging:** run `backend/db/equipment_reservations.sql`, then the updated `backend/db/test_role.sql`, in the Supabase SQL editor as the project owner. Until then `test_database_tables_match_the_models` fails against Supabase (CI's `supabase-schema` job) and every SCRUM-44 API test fails there. All the results below come from a local PostgreSQL 17 built by `ci/build_test_database.py`, exactly as CI's `unittest` job builds it ([§3e](#e-limitations)).

## What this story changed

- **Database:** a new `equipment_reservations` table (`backend/db/equipment_reservations.sql`). Each row is one item and quantity reserved for one of an event's requirements, over the event's period, with who reserved it and when. Released reservations are kept, with when and why. `test_role.sql` gives the test role the new table.
- **Backend:**
  - `GET` and `POST /api/events/<id>/equipment-reservations`, in `backend/app/events/routes.py` beside the other equipment routes. Reserving locks the event, the requirement and the suitable equipment, then works out availability again from the saved data before saving anything.
  - The rules in `backend/app/resources/reservations.py`, free of Flask and the database like SCRUM-43's `availability.py`.
  - `backend/app/resources/release.py`, a rule that runs before every save. It releases reservations when an event becomes cancelled or rejected or its times change, and when a requirement is changed or removed. It works whichever code makes the change, which matters because there is no "cancel event" feature yet.
  - SCRUM-43's check (`availability.py`) now deducts what other overlapping events have reserved. SCRUM-42's edit and remove now say when they released reserved equipment.
- **Frontend:** the Equipment reservations page (`/events/:id/equipment-reservations`). The equipment requirements page links to it ("Reserve equipment" when the user can reserve for the event, otherwise "Reserved equipment"), and so does the availability check when reserving is possible. The availability check also shows how much of each item other events have reserved.
- **Docs:** assumption A8 in the SCRUM-42 and SCRUM-43 test-case documents now says what SCRUM-44 changed for them. The C4 container diagram lists equipment reservations among the stored entities.
- **Not used:** the old stub `POST /api/resources/<id>/reservations` still returns 501 ([§3d](#d-findings-for-the-team-not-part-of-scrum-44)).

## 1. Acceptance criteria satisfied

| AC | Criterion | How it is met | Automated tests | Seen in the running app |
|----|-----------|---------------|-----------------|-------------------------|
| AC1 | The staff member may select an event and view its equipment requirements and required reservation period. | From the event's equipment requirements, "Reserve equipment" opens a page with the reservation period (the event's times) and each requirement, with its technical requirements, how much is reserved and which items can be reserved. The coordinator sees it without the forms; anyone else gets 403. | TC-44-01 to 07, 36, 37, 38, 43, 45 to 47 | E2E-01, 07 · [01](SCRUM-44/01-reservation-page.png), [06](SCRUM-44/06-coordinator-view.png) |
| AC2 | The staff member can select suitable equipment and quantities, and availability is checked again when reserving. | A quantity box for each suitable item. Reserving locks the event, the requirement and the items and works out availability again from the saved data; what another event reserved in the meantime is refused. Unsuitable or unknown items, bad quantities, the same item twice, and more than the requirement needs are refused (422). | TC-44-08, 10 to 16, 39; unit rules | E2E-02 · [02](SCRUM-44/02-reserved.png) |
| AC3 | A successful reservation records the equipment, quantities, and reservation period along with the event and displays confirmation. | One row per item, with its quantity, the event's period, the event, the requirement, who and when. The confirmation names the items, quantities, requirement, event and period, and the page shows "Reserved: 3 of 3 · Fully reserved" with each reservation. | TC-44-08, 09, 39 | E2E-02 · [02](SCRUM-44/02-reserved.png) |
| AC4 | Reserved quantities are deducted from availability for incompatible overlapping events. | Another event whose period overlaps (touching doesn't count) can reserve only what is left, and the reservation page and SCRUM-43's check both show how much other events have reserved. An event's own reservations still count as available to it, and two of its requirements can't take the same units. | TC-44-17 to 21, 48; unit rules | E2E-03 · [03](SCRUM-44/03-overlapping-event.png) |
| AC5 | If the selected quantity exceeds current availability, the reservation is not created and the staff member is shown the available quantity. | HTTP 409 with "Only 1 × … is available for this event's period, not 2. Nothing was reserved.", the shortfall for each item and what can be reserved in all. Nothing is saved, even for the other items chosen. The page keeps the entry. | TC-44-15, 20, 22 to 24, 40 | E2E-04 · [04](SCRUM-44/04-more-than-available.png) |
| AC6 | If no suitable equipment is available, the reservation cannot be created. | The requirement says "No suitable equipment is available to reserve" and has no form. Reserving anyway is refused: 409 when every suitable item is taken, 422 for an unsuitable item. | TC-44-25, 26, 41 | E2E-05 · [02](SCRUM-44/02-reserved.png) (hologram projector) |
| AC7 | If saving fails, no reservation is confirmed, existing reservations remain unchanged, and an error explains why it failed. | The reservations and the coordinator's notification are saved in one commit. If the save fails: 503, "The equipment was not reserved, and the existing reservations are unchanged. Please try again.", no notification and no email. The page keeps the entry for a retry. | TC-44-27, 42 | E2E-06 · [05](SCRUM-44/05-save-failed.png) |
| AC8 | The event's coordinator is notified of the equipment and quantities reserved. | An in-app `equipment_reserved` notification naming each item and quantity, saved with the reservation, then an email. If the email can't be queued, the reservation still stands and the reply says `email_queued: false`. | TC-44-28, 29 | E2E-07 · [06](SCRUM-44/06-coordinator-view.png) |
| AC9 | When an event is cancelled, or an accepted change alters its equipment requirements, its reservation is released and the quantities are available again. | Released on cancellation or rejection, on a change to the event's times, and on a change to or removal of a requirement (only that requirement's reservations). Released rows are kept with when and why, and hold nothing. Saving a requirement unchanged, or changing other event details, releases nothing. | TC-44-30 to 35, 44 | E2E-08, 09 · [07](SCRUM-44/07-released-after-change.png), [08](SCRUM-44/08-released-after-cancel.png) |

**Working assumptions.** Each is tied to an open question in the test-case document; none has been agreed with the customer:

- **Q1:** reserving is by item and quantity, not individual units.
- **Q2:** the reservation period is the event's own times, with no setup or return time.
- **Q3:** only Technical Support reserve; the coordinator can view.
- **Q4:** only approved events can have equipment reserved, as for venue booking.
- **Q5:** "incompatible overlapping events" means any other event whose period overlaps.
- **Q6:** part of a requirement can be reserved, and more later, never more than it needs.
- **Q7:** reserving is Technical Support's confirmation that the technical requirements are met.
- **Q8:** nobody is notified when a reservation is released.
- **Q9:** a change to the event's times releases its reservations.
- **Q10:** reserving doesn't change SCRUM-42's arrangement status.

## 2. All test cases pass

| Suite | Command | Result |
|-------|---------|--------|
| Backend, SCRUM-44 through the API | `python -m unittest tests.test_equipment_reservation` (from `backend/`) | **41/41 pass** (TC-44-01 to 37, 49 to 52; after the review fixes, §5) |
| Backend, SCRUM-44 rules (no database) | `python -m unittest tests.test_equipment_reservation_unit` | **15/15 pass** |
| Backend, every equipment test (SCRUM-42, 43, 44) | `python -m unittest tests.test_equipment_reservation tests.test_equipment_reservation_unit tests.test_equipment_availability tests.test_equipment_availability_unit tests.test_equipment_requirements` | **120/120 pass** (25 Oct 2026) |
| Backend, whole suite | `python -m unittest discover` | Before the review: **Ran 927 tests: OK, 3 skipped.** After the review fixes (25 Oct 2026): **Ran 935: all pass except 4 that check the test login itself** (three in `test_app_factory` and `test_venue_booking_rejection`'s `setUpClass`). They fail because that run used the local database's owner login, not `connectsphere_test` (§5). The 3 skips are SCRUM-36/37 tests waiting on customer answers. |
| Frontend, SCRUM-44 | `npx vitest run` on the three files below | **25/25 pass**: `EquipmentReservationPage.test.jsx` 19, the links in `EquipmentRequirementsPage.test.jsx` 3, and `EquipmentAvailabilityPage.test.jsx` 3 (58/58 across the three files) |
| Frontend, whole suite | `npm test` (from `frontend/`) | **448/449 pass.** The one failure is SCRUM-84's `VenueSetupTurnaround.test.jsx`. It fails the same way with this story's changes removed (§3d; checked again 25 Oct 2026). |
| End-to-end in a real browser | [scripts/e2e_check.mjs](SCRUM-44/scripts/e2e_check.mjs) | **9/9 pass** (§3c), [raw result](SCRUM-44/e2e-results.txt) |

## 3. Test cases are correct and the code does what it says

### a. The test cases match the acceptance criteria

- Every AC traces to test cases (see the traceability matrix in the test-case document), and every automated test names its `TC-44-xx` ID.
- The tests were written first. Commit `f0b71f8` ("TDD, red") holds only the test-case document and the tests. Against that commit **none of the 51 backend tests pass**: they fail or error because the model, the rules and the routes didn't exist. In the frontend, the page's test file couldn't load and the 4 new link and availability tests failed, while the 33 existing tests in those files passed. The green commit made them all pass.
- The API tests use the real schema, and add a per-run suffix to every category and type because the equipment catalogue is shared with real data. They assert exact rows, quantities, messages and the SQL locks, and that refusals and failed saves leave the database unchanged.
- **Two SCRUM-43 tests were adjusted.** `test_tc_43_12_…` and `test_nothing_says_reserved_booked_or_confirmed` checked that the word "reserved" appears nowhere in the availability result, field names included. The new `reserved_for_other_events` number tripped them. They now check the text shown (labels, notes and messages) rather than the field names, which is what SCRUM-43's AC4 is about. They still fail if any label or message says reserved, booked or confirmed.
- **One SCRUM-44 test was strengthened** before the mutation check: "sends only the items given a quantity" used the projector, which has only one item, so it couldn't tell whether empty items were sent. It now uses the two microphones (mutation F4 confirms it).

### b. The tests catch broken code (mutation check)

Each row is a deliberate bug put into the code, one at a time. The tests were run against it, then the file was restored byte for byte. After the last one, every test passed again. Runner: [SCRUM-77/scripts/mutation_check.py](SCRUM-77/scripts/mutation_check.py). Mutations: [scripts/mutations.py](SCRUM-44/scripts/mutations.py). Raw output: [backend](SCRUM-44/mutation-results-backend.txt), [frontend](SCRUM-44/mutation-results-frontend.txt). The backend runs included the SCRUM-42 and SCRUM-43 tests.

| ID | Deliberate bug | Should break | Caught? | Failing tests (examples) |
|----|----------------|--------------|---------|--------------------------|
| B1 | Other events' reservations are not deducted | AC4 | ✅ | `test_tc_44_17_…`, `test_reserved_quantities_are_deducted_from_each_item` (+more) |
| B2 | An event's own reservations count against it | AC4 | ✅ | `test_tc_44_11_…`, `test_tc_44_19_…` |
| B3 | Released reservations still hold equipment | AC9 | ✅ | `test_tc_44_30_…`, `test_tc_44_31_…`, `test_tc_44_33_…` |
| B4 | Reservations count whatever their period, so touching ones overlap | AC4 | ✅ | `test_tc_44_18_…`, `test_tc_44_19_…` |
| B5 | What the event already reserved isn't taken off what it can still reserve | AC2, AC4 | ✅ | `test_tc_44_10_…`, `test_tc_44_11_…`, `test_tc_44_21_…` |
| B6 | The availability check ignores reservations | AC4 | ✅ | `test_tc_44_19_…` |
| B7 | Availability isn't checked again when reserving | AC2 | ✅ | `test_tc_44_15_availability_is_checked_again_when_reserving` (+2) |
| B8 | The chosen equipment isn't locked before checking | AC2 (A7) | ✅ | `test_tc_44_16_…` |
| B9 | Unsuitable equipment can be reserved | AC2 | ✅ | `test_tc_44_13_…`, `test_tc_44_25_…` (+1) |
| B10 | The same item can be chosen twice | AC2 | ✅ | `test_tc_44_13_…` (+1) |
| B11 | A quantity of 0 is accepted | AC2 | ✅ | `test_tc_44_13_…` (+1) |
| B12 | A requirement can get more than it needs | AC2 (A6) | ✅ | `test_tc_44_13_…` (+1) |
| B13 | A fully reserved requirement isn't refused as such | AC2 (A6) | ✅ | `test_tc_44_12_…` |
| B14 | The reservation period isn't the event's | AC3 | ✅ | `test_tc_44_08_…` (+more) |
| B15 | The confirmation leaves out the period | AC3 | ✅ | `test_tc_44_09_…` |
| B16 | More than available can be reserved | AC5 | ✅ | `test_tc_44_15_…`, `test_tc_44_20_…` (+more) |
| B17 | The refusal doesn't give the available quantity | AC5 | ✅ | `test_tc_44_15_…`, `test_tc_44_20_…` (+more) |
| B18 | Reserving goes on when no suitable equipment is available | AC6 | ✅ | `test_tc_44_26_…` |
| B19 | A failed save is reported as saved | AC7 | ✅ | `test_tc_44_27_…` |
| B20 | The email is queued before the reservation is saved | AC7 (A9) | ✅ | `test_tc_44_27_…`, `test_tc_44_28_…` |
| B21 | The coordinator gets no in-app notification | AC8 | ✅ | `test_tc_44_28_…` (+2) |
| B22 | The coordinator gets no email | AC8 | ✅ | `test_tc_44_28_…` |
| B23 | Cancelling an event doesn't release its reservations | AC9 | ✅ | `test_tc_44_30_…` |
| B24 | Changing a requirement doesn't release its reservations | AC9 | ✅ | `test_tc_44_31_…` |
| B25 | Removing a requirement doesn't release its reservations | AC9 | ✅ | `test_tc_44_33_…` |
| B26 | Changing the event's times doesn't release its reservations | AC9 (A10) | ✅ | `test_tc_44_34_…` |
| B27 | Any change to an event releases its reservations | AC9 (A10) | ✅ | `test_tc_44_35_…` |
| B28 | A release doesn't record when | AC9 | ✅ | `test_tc_44_30_…` |
| B29 | SCRUM-42's edit doesn't say the reservation was released | AC9 | ✅ | `test_tc_44_31_…` |
| B30 | Anyone may reserve | AC2 (A3) | ✅ | `test_tc_44_36_…` |
| B31 | Anyone may view the reservations | AC1 (A3) | ✅ | `test_tc_44_05_…` |
| B32 | The coordinator is offered reserving | AC1 (A3) | ✅ | `test_tc_44_03_…` |
| B33 | Events that aren't approved can be reserved for | AC1 (A4) | ✅ | `test_tc_44_37_…` |
| B34 | A failed load is shown as an empty page | AC1 | ✅ | `test_tc_44_07_…` |
| F1 | No form to reserve with | AC2 | ✅ | reserves the chosen quantities and shows the confirmation (+6) |
| F2 | A form is offered when nothing can be reserved | AC6 | ✅ | says when no suitable equipment is available and offers nothing to reserve |
| F3 | The coordinator is offered the form | AC1 | ✅ | shows the coordinator the reservations without a way to reserve (+1) |
| F4 | Every item is sent, with or without a quantity | AC2 | ✅ | sends only the items given a quantity |
| F5 | The reservation period is not shown | AC1 | ✅ | shows the reservation period and what can be reserved for each requirement |
| F6 | How much is reserved is not shown | AC3 | ✅ | reserves the chosen quantities and shows the confirmation (+2) |
| F7 | Other events' reservations are not explained on the page | AC4 | ✅ | says how much of an item other events and this event have reserved |
| F8 | The confirmation is not shown | AC3 | ✅ | reserves the chosen quantities and shows the confirmation (+2) |
| F9 | A refusal is not shown | AC5, AC7 | ✅ | shows the available quantity when more is chosen than is available (+2) |
| F10 | The entry is cleared after a failed save | AC7 | ✅ | keeps the selection after a failed save so it can be tried again (+1) |
| F11 | Released reservations are not listed | AC9 | ✅ | lists released reservations with the reason |
| F12 | A page for the previous event can show under the next | AC1 | ✅ | shows only the event in the address, even when the previous event's page arrives last |
| F13 | The availability check hides other events' reservations | AC4 | ✅ | shows how much of each item other events have reserved |
| F14 | Technical Support and the coordinator get the same link | AC1 | ✅ | links Technical Support Staff to reserving equipment (+1) |

**Result: 48/48 caught** (backend 34/34, frontend 14/14).

### c. The running app does what it says (end-to-end)

Run against the real app: the Vite dev server and the Flask API, with the API on a local PostgreSQL 17 database (`scrum44_e2e`) built by `ci/build_test_database.py`, because the new table isn't on Supabase yet. A script drove Microsoft Edge with Playwright as `demo.tech` (Technical Support) and `demo.coordinator`, on fresh events from [scripts/seed_demo_reservations.py](SCRUM-44/scripts/seed_demo_reservations.py), which refuses any database not on this machine. The API log for the run has no errors.

Demo data: microphones "[Demo] Shure SLX-D 44" (2) and "[Demo] Sennheiser EW-D 44" (2, category written "[demo]  wireless MICROPHONE"); projectors "[Demo] BenQ LU935 44" (2) and "[Demo] Epson EB-L 44" (1, unavailable 5 Dec 2026 17:00–19:00, "Lamp replacement"). The "[Demo] Charity Gala" runs 5 Dec 2026 18:00–23:00 and needs 3 microphones ("Lapel"), 1 projector and 1 hologram projector. The overlapping "[Demo] Winter Concert" runs 20:00–23:30 and needs 2 microphones.

| ID | Check | Result | Screenshot |
|----|-------|--------|------------|
| E2E-01 | From the gala's equipment requirements, Technical Support open "Reserve equipment". They see the period "05/12/2026 18:00 SGT to 05/12/2026 23:00 SGT", "Reserved: 0 of 3", the Shure with 2 to reserve, "Lapel" to confirm, and the Epson as not available with its reason. | PASS | [01](SCRUM-44/01-reservation-page.png) |
| E2E-02 | Reserving 2 Shure and 1 Sennheiser confirms them with the period and says the coordinator was notified. The page shows "Reserved: 3 of 3 · Fully reserved". The API returns both rows with the event's period, `reserved`. | PASS | [02](SCRUM-44/02-reserved.png) |
| E2E-03 | The concert's page shows "Shure … 0 available to reserve (2 recorded, 2 reserved for other events at this time)" and the Sennheiser with 1. Its availability check shows "Available: 1" and the Shure as "0 of 2; 2 reserved for other events at this time". | PASS | [03](SCRUM-44/03-overlapping-event.png) |
| E2E-04 | Asking for 2 Sennheisers for the concert shows "Only 1 × [Demo] Sennheiser EW-D 44 is available for this event's period, not 2. Nothing was reserved." The entry stays at 2, and the concert has nothing reserved. | PASS | [04](SCRUM-44/04-more-than-available.png) |
| E2E-05 | The gala's hologram projector says "No suitable equipment is available to reserve", with no quantity box or button. | PASS | [02](SCRUM-44/02-reserved.png) |
| E2E-06 | With the save cut off before it reaches the server, the page shows "The equipment was not reserved…" and keeps the entry; the gala's reservations are unchanged. | PASS | [05](SCRUM-44/05-save-failed.png) |
| E2E-07 | `demo.coordinator` has an `equipment_reserved` notification naming both items, the requirement and the gala. Through "Reserved equipment" they see who reserved what, with no way to reserve. | PASS | [06](SCRUM-44/06-coordinator-view.png) |
| E2E-08 | The coordinator changes the microphones to 4 and is told "Its reserved equipment was released." The concert can reserve 2 Shure again, and the gala lists the two released with "The equipment requirement was changed." | PASS | [07](SCRUM-44/07-released-after-change.png) |
| E2E-09 | Technical Support reserve 2 Shure for the concert (the gala then has 0 Shure to reserve), and the concert is cancelled through the app's models (there's no screen for it yet). The gala can reserve 2 Shure again, and the concert says it is cancelled and lists the reservation as released, "The event was cancelled." | PASS | [08](SCRUM-44/08-released-after-cancel.png) |

**First run: 8/9.** E2E-02 failed because of the script, not the app. It expected the Shure row first, but the page lists items by name, so the Sennheiser was sent and saved first. The rows themselves were right (checked through the API). The script now compares them in any order. The second run, on freshly seeded events, passed 9/9; the screenshots are from that run.

### d. Findings for the team (not part of SCRUM-44)

1. **A SCRUM-84 frontend test fails on `main`.** `VenueSetupTurnaround.test.jsx` › "sends the setup and turnaround and shows the labelled conflict, keeping the entries" throws `Cannot read properties of undefined (reading 'filter')` and can't find the "Venue" field. It fails the same way with this story's changes stashed. CI doesn't run frontend tests, so it went unnoticed. The likeliest cause is SCRUM-69's change to `VenueBookingRequestPage.jsx` (PR #49), as the test's mock may not return what the page now expects. Not changed here.
2. **The stub `POST /api/resources/<id>/reservations` is still a stub (501).** It reserves one item, but a SCRUM-44 reservation is for an event's requirement and may take several items at once, saved together or not at all. So reserving lives at `POST /api/events/<id>/equipment-reservations`, beside SCRUM-42's and SCRUM-43's routes. The team may want to remove the stub, or point it here, so nobody builds a second way to reserve.
3. **There is no way to cancel an event yet.** The release rule runs whenever an event's status becomes cancelled or rejected, whichever code does it, so a future cancel feature needs nothing extra for AC9. The same goes for SCRUM-46 change requests: once accepting one changes a requirement or the event's times, its reservations are released.
4. **Not every test can run against Supabase.** `test_venue_booking_rejection.RejectionPersistenceTests` refuses to run unless the test database is a local Docker one on port 5432 (or 127.0.0.1:5433), so a local run on any other port errors in `setUpClass`.

### e. Limitations

- **Not yet run against Supabase.** The new table must be created there first (see the note at the top). The local database is built from the same models CI uses, and `db/equipment_reservations.sql` matches the model (columns, constraints, indexes, `on delete set null`). After the scripts are run, `python -m unittest tests.test_app_factory tests.test_equipment_reservation` against Supabase should be run once before merging.
- **Concurrency is shown, not stress-tested.** TC-44-16 confirms that the event, requirement and items are read `FOR UPDATE` before the reservation is inserted, and TC-44-15 that a reservation made in between is seen. Two reservations racing at the same moment were not simulated.
- The demo accounts used in the browser check were created in the local database only; the Supabase demo accounts were not touched.

## 4. Evidence documented

- This document, and the test-case document with its traceability matrix and open questions.
- [SCRUM-44/](SCRUM-44/): screenshots `01`–`08`; `scripts/` (seed script, browser check, mutations); `mutation-results-backend.txt`, `mutation-results-frontend.txt`, `e2e-results.txt`.
- Commits: `f0b71f8` (TDD, red) and the TDD-green commit that follows it on this branch.

## 5. Review fixes (25 Oct 2026)

Every point in the code review was checked against the code and found to be accurate. Each was fixed test-first: the new tests (TC-44-49 to 56, plus a unit rule) failed before the fix and pass after it.

| Review point | Fix | Tests |
|---|---|---|
| A failed reload after reserving was never shown | The page shows the load error, with Retry, even when it still has the old page | TC-44-54 |
| Wrong requirement labels when the event can't be reserved for | New state *not reservable*, "Equipment can't be reserved for this event now", used whenever the page has a notice (not approved, or no times) | TC-44-04, 49; unit rule |
| Coordinator not told about a release made in a race | Editing and removing a requirement lock it before looking for its reservations | TC-44-51 |
| Old numbers after a refusal; stale errors under other requirements | A 409 reloads the page, keeping the refusal and the quantities typed; a successful reservation clears every earlier refusal | TC-44-55, 56 |
| Setting the same value after a commit released reservations | `release._changed` compares with the saved row when the old value wasn't loaded | TC-44-52 |
| "Reserve equipment" links where nothing can be reserved | Both pages return `can_reserve` (same rule as reserving); the requirements page shows "Reserved equipment" otherwise, and the availability check shows no link | TC-44-50, 53 |
| Catalogue loaded repeatedly | `_suitable_resources` narrows the catalogue in SQL by the same key as `availability.match_key`; `is_suitable` still decides | Existing TC-44-02, 16, 19, 25 |
| Extra SUM query | The requirement's reserved total comes from the event's reservations, which are loaded anyway | Existing TC-44-11, 12 |
| Copied lookup | `_event_requirement(..., lock=True)`, as `_own_draft`; `_locked_requirement` removed | Existing TC-44-14, 16 |
| Test helper imported from a test module | `texts` moved to `tests/payloads.py` | SCRUM-43 tests |

**How it was run.** The backend tests used the local PostgreSQL 17, logged in as its owner, because the password set for the local `connectsphere_test` role wasn't recorded. Four tests check the login itself and fail for that reason alone (§2). CI's `unittest` job runs as `connectsphere_test` and covers them. **Not re-run after the fixes:** the mutation check (§3b) and the browser check (§3c).
