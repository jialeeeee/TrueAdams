# SCRUM-43 — Check Equipment Availability for an Event: Test Cases

**User story:** As a Technical Support Staff member, I want to view all available equipment so that I can determine whether an event's equipment requirements can be fulfilled.

**Created:** 21 Oct 2026 · **Status of all cases:** automated cases pass (21 Oct 2026, Supabase + Vitest); end-to-end check passed in the browser, see [the DoD evidence](../evidence/SCRUM-43-dod-evidence.md) · **Automated tests:** `backend/tests/test_equipment_availability.py` (through the API), `backend/tests/test_equipment_availability_unit.py` (the rules, no database), `frontend/src/pages/EquipmentAvailabilityPage.test.jsx` (+ the link in `EquipmentRequirementsPage.test.jsx`) · **Endpoint:** `GET /api/events/<id>/equipment-availability` · **Related:** SCRUM-42 (the requirements checked here), SCRUM-44 (reserving; it will deduct reservations from the same check), SCRUM-84 (setup and turnaround time, venues only)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The check uses the event's equipment types, quantities, technical requirements, and required date and start/end times. |
| AC2 | The result shows the requested quantity and available suitable quantity for each equipment requirement. |
| AC3 | Equipment recorded as unavailable for the required period is excluded. |
| AC4 | Checking availability does not create a reservation. |
| AC5 | Missing timing information or a failed availability check produces an error with details. |

## Working assumptions (to confirm)

- **A1 — What is checked:** every equipment requirement recorded for the event (SCRUM-42), over the event's start and end time (Singapore time, half-open `[start, end)`). The check is read-only and runs each time it is asked for, from the saved data.
- **A2 — Suitable equipment:** an item in the equipment catalogue (`resources`) whose **category** matches the requirement's equipment type, ignoring case and spacing (as SCRUM-42 A6). Its name is not matched. *(Q1)*
- **A3 — Technical requirements:** they are free text on both sides, so they are **shown** on each line for Technical Support to judge, but not matched automatically. The line says so. Because of that, a requirement with technical requirements is never reported as plain *enough*: if there is enough by category, its result is `enough_by_category`, "Enough by category; technical requirements still to be checked", and the summary counts it separately from the requirements that can be met (added after the review of PR #48). *(Q2)*
- **A4 — Available suitable quantity:** the sum of `quantity_available` of the suitable items that are not excluded. An item with no quantity recorded (NULL) is excluded and listed as "quantity not recorded", never counted as available. *(Q3)*
- **A5 — Recorded unavailability:** a new `equipment_unavailability` table (`db/equipment_unavailability.sql`) records periods when an item cannot be used (e.g. repair), with a reason. An item with a period that overlaps the event's `[start, end)` is excluded **as a whole** and listed with the reason and period. Touching periods do not overlap. Recording these periods is not part of this story: there is no screen or endpoint for it yet. *(Q4, Q5)*
- **A6 — No setup time:** equipment is needed only for the event's own start and end time; SCRUM-84's setup and turnaround times apply to venues. *(Q6)*
- **A7 — Result per requirement:** `enough` (available ≥ requested), `not_enough` (some, but fewer than requested) or `none_suitable` (no suitable item is available). An overall summary says how many requirements can be met. Nothing in the result says reserved, booked or confirmed.
- **A8 — Reservations:** none exist until SCRUM-44, which will deduct reserved quantities from the same calculation. This story only reads.
- **A9 — Who can check:** Technical Support Staff (`tech_staff`) only, as the story says. Everyone else gets HTTP 403 without the event's details. *(Q7)*
- **A10 — Errors, first failure wins:** 401 (no valid user) → 404 (no such event) → 403 (not Technical Support) → 409 (cancelled or rejected event: there is nothing to arrange) → 422 (start or end time not recorded: `missing` names them) → 503 (the check could not be completed: `retryable: true`, nothing else returned). An event with no requirements is not an error: it returns no lines and says so.
- **A11 — Shared stock:** requirements of the same event whose types match the same equipment (the same type, ignoring case and spacing) draw on one stock: together they can't count the same items twice. If together they ask for more than is available, none of them is *enough*; each line says which requirements it shares with and how many they need together. No requirement is given priority over another (added after the review of PR #48). *(Q8)*

## Seed data (AV-SEED)

Users: `USERS` from `backend/tests/seed_data.py` (hana is tech staff; alice is G1's coordinator).

Events (organiser dana, coordinator alice):

| Key | Event | Status | Start – end (Singapore time) |
|-----|-------|--------|------------------------------|
| G1 | Charity Gala | approved | 2026-12-05 18:00 – 23:00 |
| G2 | Untimed Talk | submitted | not recorded |
| G3 | Spring Fair | cancelled | 2026-11-01 10:00 – 16:00 |

G1's requirements: **3 × Wireless microphone** ("Lapel"), **1 × Projector**, **1 × Hologram projector**, **2 × Speaker**.

Equipment (category · quantity available · recorded unavailability):

| Item | Category | Available | Unavailable |
|------|----------|-----------|-------------|
| Shure SLX-D | Wireless microphone | 2 | — |
| Sennheiser EW-D | "wireless  MICROPHONE" | 2 | — |
| Epson EB-L | Projector | 1 | 2026-12-05 17:00 – 19:00 "Lamp replacement" (overlaps) |
| BenQ LU935 | Projector | 2 | 2026-12-05 23:00 – 2026-12-06 09:00 (touches the end: not overlapping) |
| JBL EON | Speaker | not recorded | — |
| Bose S1 | Speaker | 1 | — |

The equipment catalogue is shared with real data (it already holds a demo "Wireless microphone"), so the automated tests add a per-run suffix to every category and equipment type.

Expected for G1: microphones 3 requested, **4** available (enough by category; "Lapel" still to be checked); projector 1 requested, **2** available (enough; Epson excluded); hologram projector 1 requested, **0** (no suitable equipment); speakers 2 requested, **1** available (not enough; JBL excluded, quantity not recorded). Overall: 1 of 4 requirements can be met, and 1 more has enough by category but its technical requirements are still to be checked.

---

## AC1 — The check uses the event's requirements and times

**TC-43-01 · One line per requirement, with its type, quantity and technical requirements, for the event's period**
- **Traces to:** AC1, AC2 · **Type:** Positive
- **Steps:** As hana, check G1.
- **Expected result:** HTTP 200 with G1's title and period (2026-12-05 18:00 – 23:00), and four lines in the order the requirements were recorded, each with its equipment type, requested quantity and technical requirements.
- **Automated:** `test_tc_43_01_one_line_per_requirement_for_the_events_period`

**TC-43-02 · The latest saved requirements and times are used**
- **Traces to:** AC1 · **Type:** Positive
- **Steps:** Check G1. Change the microphones to 5 and G1's start to 2026-12-05 20:00, then check again.
- **Expected result:** The microphones now show 5 requested and *not enough*. The projector line now counts the Epson (its unavailability ends at 19:00, before the new start).
- **Automated:** `test_tc_43_02_uses_the_latest_saved_requirements_and_times`

**TC-43-03 · Types match categories ignoring case and spacing; other categories don't count**
- **Traces to:** AC1, AC2 · **Type:** Positive · **Depends on:** A2
- **Steps:** Check G1.
- **Expected result:** Both microphone items (one with category "wireless  MICROPHONE") are suitable for the microphones; no projector or speaker is.
- **Automated:** `test_tc_43_03_types_match_categories_ignoring_case_and_spacing`

**TC-43-04 · Technical requirements are shown, not matched**
- **Traces to:** AC1 · **Type:** Positive · **Depends on:** A3
- **Steps:** Check G1.
- **Expected result:** The microphone line includes "Lapel" and a note that Technical Support must confirm the technical requirements.
- **Automated:** `test_tc_43_04_technical_requirements_are_shown_for_technical_support_to_confirm`

## AC2 — Requested and available suitable quantity per requirement

**TC-43-05 · Requested and available quantities, and whether there are enough**
- **Traces to:** AC2 · **Type:** Positive · **Depends on:** A4, A7
- **Steps:** Check G1.
- **Expected result:** Microphones 3 / 4 *enough by category* (they have technical requirements); projector 1 / 2 *enough*; hologram projector 1 / 0 *none suitable*; speakers 2 / 1 *not enough*. The summary says 1 of 4 requirements can be met and 1 more has enough by category, with its technical requirements still to be checked.
- **Automated:** `test_tc_43_05_requested_and_available_quantity_for_each_requirement`

**TC-43-06 · Exactly enough is enough**
- **Traces to:** AC2 · **Type:** Boundary
- **Steps:** Change the projector to 2 and check G1. (The projector has no technical requirements, so enough is simply enough.)
- **Expected result:** 2 requested, 2 available, *enough*, "Enough available".
- **Automated:** `test_tc_43_06_exactly_enough_is_enough`

**TC-43-07 · Equipment with no quantity recorded is not counted**
- **Traces to:** AC2 · **Type:** Negative · **Depends on:** A4
- **Steps:** Check G1.
- **Expected result:** The JBL EON is listed as excluded ("quantity not recorded") on the speaker line; only the Bose's 1 is counted.
- **Automated:** `test_tc_43_07_equipment_with_no_quantity_recorded_is_not_counted`

**TC-43-08 · An event with no requirements says so**
- **Traces to:** AC2 · **Type:** Positive (empty)
- **Steps:** As hana, check an approved, timed event with no requirements.
- **Expected result:** HTTP 200, no lines, and "No equipment requirements have been recorded for this event."
- **Automated:** `test_tc_43_08_an_event_with_no_requirements_says_so`

**TC-43-23 · Requirements for the same equipment share its stock** *(added after the review of PR #48)*
- **Traces to:** AC1, AC2 · **Type:** Business rule · **Depends on:** A11
- **Steps:** Add 3 × Wireless microphone ("Handheld") to G1 (it already needs 3 × Wireless microphone, "Lapel"; there are 4 microphones), and check G1.
- **Expected result:** Both microphone lines show 3 requested, 4 available, together 6 requested, and *not enough*, each naming the other requirement it shares with. The projector line shares with nothing. The summary says 1 of 5 requirements can be met.
- **Automated:** `test_tc_43_23_requirements_for_the_same_equipment_share_its_stock`

**TC-43-24 · Enough by category is not the same as technically suitable** *(added after the review of PR #48)*
- **Traces to:** AC1, AC2 · **Type:** Business rule · **Depends on:** A3
- **Steps:** Check G1. Remove the microphones' technical requirements and check again.
- **Expected result:** The microphones ("Lapel") are *enough by category*, "Enough by category; technical requirements still to be checked"; the projector (no technical requirements) is *enough*. Without technical requirements the microphones are *enough*.
- **Automated:** `test_tc_43_24_enough_by_category_is_not_confirmed_technical_suitability`

## AC3 — Equipment unavailable for the period is excluded

**TC-43-09 · An item unavailable during the event is excluded, with the reason**
- **Traces to:** AC3 · **Type:** Positive · **Depends on:** A5
- **Steps:** Check G1.
- **Expected result:** The Epson EB-L is not counted on the projector line and is listed as excluded with "Lamp replacement" and its period.
- **Automated:** `test_tc_43_09_equipment_unavailable_during_the_event_is_excluded`

**TC-43-10 · A period that only touches the event does not exclude**
- **Traces to:** AC3 · **Type:** Boundary · **Depends on:** A5
- **Steps:** Check G1.
- **Expected result:** The BenQ LU935 (unavailable from 23:00, when G1 ends) is counted.
- **Automated:** `test_tc_43_10_a_period_that_only_touches_the_event_does_not_exclude`

**TC-43-11 · Unavailability on another day does not exclude**
- **Traces to:** AC3 · **Type:** Boundary
- **Steps:** Record the Shure unavailable on 2026-12-04 and check G1.
- **Expected result:** The Shure is still counted (microphones 4 available).
- **Automated:** `test_tc_43_11_unavailability_on_another_day_does_not_exclude`

## AC4 — Checking does not reserve

**TC-43-12 · Checking changes nothing**
- **Traces to:** AC4 · **Type:** Business rule · **Depends on:** A8
- **Steps:** Check G1 twice.
- **Expected result:** Every item's available quantity, every requirement (quantity and arrangement status) and G1 itself are unchanged; both results are the same; nothing in the result says reserved, booked or confirmed, and the result says checking does not reserve any equipment.
- **Automated:** `test_tc_43_12_checking_changes_nothing_and_reserves_nothing`

## AC5 — Missing times and failed checks give an error with details

**TC-43-13 · Missing start or end time**
- **Traces to:** AC5 · **Type:** Negative · **Depends on:** A10
- **Steps:** As hana, check G2 (no times). Then give G2 a start time only and check again.
- **Expected result:** HTTP 422 saying the times are needed, with `missing` naming `start_time` and `end_time`, then only `end_time`. No lines are returned.
- **Automated:** `test_tc_43_13_missing_times_are_an_error_naming_them`

**TC-43-14 · A failed check is an error, not a result**
- **Traces to:** AC5 · **Type:** Negative (failure) · **Depends on:** A10
- **Steps:** Make reading the equipment catalogue fail, then the unavailability, and check G1 each time.
- **Expected result:** HTTP 503, `retryable: true`, an error saying the check could not be completed, no internal error text, and no lines or summary.
- **Automated:** `test_tc_43_14_a_failed_check_is_an_error_not_a_result`

**TC-43-15 · Who may check, and in what order**
- **Traces to:** AC5 · **Type:** Negative (authorisation) · **Depends on:** A9, A10
- **Steps:** Check G1 without a token and with a deleted user's token; a missing event as hana; G1 as alice, dana, gus, admin and farah; G3 (cancelled) as hana; G2 (no times) as alice.
- **Expected result:** 401; 404; 403 with no event details; 409 naming the status; 403 (permission comes before the missing times).
- **Automated:** `test_tc_43_15_who_may_check_and_in_what_order`

## The rules without a database (`test_equipment_availability_unit.py`)

The same rules, run on plain objects: matching ignores case and spacing (A2); a NULL quantity is excluded (A4); an item with an unavailable period is excluded, with the reason (A5; which periods overlap is decided in the database query by `scheduling.overlapping()`, covered by TC-43-09 to 11); the result is `enough` at exactly the requested quantity, `not_enough` below it and `none_suitable` at 0 (A7); the summary counts the requirements that can be met. **Automated:** `EquipmentAvailabilityRuleTests`.

## Frontend

`EquipmentAvailabilityPage` (`/events/:eventId/equipment-availability`), linked from the equipment requirements page for Technical Support Staff.

**TC-43-16 · The check shows each requirement's requested and available quantity and the result** — AC1, AC2 · `shows each requirement with its requested and available quantity`

**TC-43-17 · Excluded equipment is listed with the reason** — AC3 · `lists the equipment excluded and why`

**TC-43-18 · The page says checking does not reserve anything** — AC4 · `says that checking does not reserve any equipment`

**TC-43-19 · Missing times are explained, with no result** — AC5 · `explains missing times without showing a result`

**TC-43-20 · A failed check offers Retry; a refusal does not** — AC5 · `offers Retry after a failed check` and `shows a refusal without Retry`

**TC-43-21 · Technical Support reach the check from the equipment requirements page; the coordinator isn't offered it** — AC1 · `EquipmentRequirementsPage` "links Technical Support Staff to the availability check" and "does not offer the check to the coordinator"

**TC-43-22 · Moving to another event shows only that event's result** *(added with the stale-result fix from the review of SCRUM-42's PR #47)* — AC1, AC2 · `shows only the event in the address, even when the previous event's result arrives last`, and `hides Check again while a check is running` (why two checks for one event can't overlap)

**TC-43-25 · Shared stock is explained on the page** *(added after the review of PR #48)* — AC2 · `says when requirements share the same equipment, and that together they need more`

Also: `explains a failed check without a server message`, `says when the event has no requirements to check`.

---

## Traceability matrix

| AC | Test cases |
|----|------------|
| AC1 | 01, 02, 03, 04, 16, 21, 22, 23, 24 |
| AC2 | 01, 03, 05, 06, 07, 08, 16, 22, 23, 24, 25 |
| AC3 | 09, 10, 11, 17 |
| AC4 | 12, 18 |
| AC5 | 13, 14, 15, 19, 20 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Is an item suitable when its category matches the requirement's equipment type (as built), or should types and categories come from one defined list? | A2, TC-43-03 |
| Q2 | Should technical requirements be matched automatically? That needs equipment specifications recorded in a structured way; today both sides are free text. | A3, TC-43-04 |
| Q3 | Should equipment with no quantity recorded be shown as "unable to assess" for the whole requirement, rather than excluded? | A4, TC-43-07 |
| Q4 | Can only part of an item's stock be unavailable (e.g. 2 of 5 microphones in repair)? As built, a period makes the whole item unavailable. | A5 |
| Q5 | Who records equipment unavailability, and where? (No story covers it yet.) | A5 |
| Q6 | Does equipment need setup or return time around the event, like venues (SCRUM-84)? | A6, TC-43-10 |
| Q7 | Should the event's coordinator also be able to run the check? | A9, TC-43-15 |
| Q8 | When requirements for the same equipment together need more than there is, should some of them be met first (for example in the order recorded), rather than none being reported as enough (as built)? | A11, TC-43-23 |
