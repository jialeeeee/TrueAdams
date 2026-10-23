# SCRUM-44 — Reserve Equipment for an Event: Test Cases

**User story:** As a Technical Support Staff member, I want to reserve available equipment for an event so that its equipment needs are secured without overallocation of equipment.

**Created:** 23 Oct 2026 · **Status of all cases:** written, automated tests failing until the story is built (TDD, red) · **Automated tests:** `backend/tests/test_equipment_reservation.py` (through the API), `backend/tests/test_equipment_reservation_unit.py` (the rules, no database), `frontend/src/pages/EquipmentReservationPage.test.jsx` (+ the links in `EquipmentRequirementsPage.test.jsx` and the reserved quantities in `EquipmentAvailabilityPage.test.jsx`) · **Endpoints:** `GET` and `POST /api/events/<id>/equipment-reservations` · **Related:** SCRUM-42 (the requirements reserved for; changing one releases its reservation), SCRUM-43 (the availability check, which now deducts reservations), SCRUM-46 (change requests; an accepted change goes through the same release rule)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The staff member may select an event and view its equipment requirements and required reservation period. |
| AC2 | The staff member can select suitable equipment and quantities, and availability is checked again when reserving. |
| AC3 | A successful reservation records the equipment, quantities, and reservation period along with the event and displays confirmation. |
| AC4 | Reserved quantities are deducted from availability for incompatible overlapping events. |
| AC5 | If the selected quantity exceeds current availability, the reservation is not created and the staff member is shown the available quantity. |
| AC6 | If no suitable equipment is available, the reservation cannot be created. |
| AC7 | If saving fails, no reservation is confirmed, existing reservations remain unchanged, and an error explains why it failed. |
| AC8 | The event's coordinator is notified of the equipment and quantities reserved. |
| AC9 | When an event is cancelled, or an accepted change alters its equipment requirements, its reservation is released and the quantities are available again. |

## Working assumptions (to confirm)

- **A1 — What is reserved:** items from the equipment catalogue (`resources`) for one of the event's recorded equipment requirements (SCRUM-42) at a time. An item is suitable when its category matches the requirement's equipment type, ignoring case and spacing, as in SCRUM-43 A2. One reservation may use several items, e.g. 2 × Shure SLX-D and 1 × Sennheiser EW-D for 3 × Wireless microphone; each item and quantity is recorded as its own row of the new `equipment_reservations` table (`db/equipment_reservations.sql`). *(Q1)*
- **A2 — Reservation period:** the event's start and end time (Singapore time, half-open `[start, end)`), with no setup or return time (SCRUM-43 A6). It is recorded on the reservation. *(Q2)*
- **A3 — Who:** Technical Support Staff (`tech_staff`) reserve. The event's coordinator can view the reservations but not reserve. Everyone else gets HTTP 403 without the event's details. *(Q3)*
- **A4 — Which events:** only **approved** events can have equipment reserved, as only approved events can have a venue booked (SCRUM-39). Other events can be viewed; the page says why nothing can be reserved, and reserving is refused with 409. *(Q4)*
- **A5 — What can be reserved:** for each suitable item, its recorded quantity, less what is reserved for **other events whose reservation periods overlap** this one (the "incompatible overlapping events"), less what this event has already reserved of it for any of its requirements. Periods that only touch don't overlap. An item recorded as unavailable during the period (SCRUM-43 A5), or with no quantity recorded (SCRUM-43 A4), has nothing to reserve. Released reservations are not counted. *(Q5)*
- **A6 — Part of a requirement:** a reservation may be for fewer than the requirement needs (for example when only 1 of 2 speakers is available); the rest can be reserved later. A requirement's reservations together can never be for more than its quantity, and a fully reserved requirement can't be reserved for again. *(Q6)*
- **A7 — Checked again when reserving:** the page shows what was available when it was loaded; reserving works it out again from the saved data, with the event, the requirement and the chosen items locked (`SELECT … FOR UPDATE`), so two staff members can't reserve the same units at once.
- **A8 — Technical requirements:** shown, not matched (SCRUM-43 A3). Choosing items and reserving them is the staff member's confirmation that they meet the technical requirements. *(Q7)*
- **A9 — Notification:** the event's coordinator gets an in-app notification (`equipment_reserved`) saved with the reservation, then an email. If the email can't be queued the reservation still stands and the reply says so (`email_queued: false`).
- **A10 — Release:** a reservation is **released**, not deleted: its status becomes `released`, with when and why, and it is kept as history. That happens when the event becomes cancelled or rejected; when one of its requirements' type, quantity or technical requirements change (today through SCRUM-42's edit; an accepted change request (SCRUM-46) will go through the same rule), only for that requirement; when a requirement is removed; and when the event's start or end time changes, because the reservation was for the old period. It is a rule applied whenever these changes are saved, whichever screen saves them, because there is no "cancel event" feature yet. Saving a requirement without changing it releases nothing. Nobody is notified of a release. *(Q8, Q9)*
- **A11 — The availability check (SCRUM-43):** now deducts what other overlapping events have reserved, and shows how much of each item is reserved for them. An event's own reservations still count as available to it.
- **A12 — Arrangement status:** reserving doesn't change SCRUM-42's arrangement status (Requested, Being arranged, Suitable equipment unavailable); how much is reserved is shown on the reservation page. *(Q10)*
- **A13 — Errors, first failure wins:** 401 (no valid user) → 404 (no such event) → 403 (not Technical Support) → 400 (the body isn't a JSON object) → 422 (`requirement_id` missing or not a whole number) → 404 (no such requirement for this event) → 409 (event not approved) → 422 (times not recorded, `missing`) → 409 (requirement already fully reserved) → 422 (the items: `fields.items`) → 409 (no suitable equipment available, `available_quantity: 0`) → 409 (more than available: `available_quantity` and `shortfalls`) → 503 (not saved: `retryable: true`).

## Seed data (RS-SEED)

Users: `USERS` from `backend/tests/seed_data.py` (hana is Technical Support; alice coordinates R1, R4 and R5; ben coordinates R2 and R3).

Events (Singapore time):

| Key | Event | Status | Start – end | Requirements |
|-----|-------|--------|-------------|--------------|
| R1 | Charity Gala | approved | 2026-12-05 18:00 – 23:00 | 3 × Wireless microphone ("Lapel"), 1 × Projector, 1 × Hologram projector, 2 × Speaker |
| R2 | Winter Concert | approved | 2026-12-05 20:00 – 23:30 (overlaps R1) | 2 × Wireless microphone |
| R3 | After-party | approved | 2026-12-05 23:00 – 2026-12-06 02:00 (touches R1's end) | 2 × Wireless microphone |
| R4 | Book Fair | submitted | 2026-12-10 09:00 – 17:00 | 1 × Wireless microphone |
| R5 | Spring Fair | cancelled | 2026-12-05 18:00 – 23:00 | 1 × Wireless microphone |

Equipment, as in SCRUM-43's AV-SEED: Shure SLX-D (Wireless microphone, 2), Sennheiser EW-D ("wireless  MICROPHONE", 2), Epson EB-L (Projector, 1, unavailable 2026-12-05 17:00 – 19:00 "Lamp replacement"), BenQ LU935 (Projector, 2), JBL EON (Speaker, quantity not recorded), Bose S1 (Speaker, 1). The automated tests add a per-run suffix to every category and type, because the catalogue is shared with real data.

Expected for R1 with nothing reserved: microphones 4 can be reserved (2 Shure, 2 Sennheiser); projector 2 (BenQ; Epson excluded); hologram projector none; speakers 1 (Bose; JBL excluded).

---

## AC1 — Select an event; view its requirements and reservation period

**TC-44-01 · The page shows the requirements and the reservation period**
- **Traces to:** AC1 · **Type:** Positive · **Depends on:** A2
- **Steps:** As hana, open R1's equipment reservations.
- **Expected result:** HTTP 200 with R1's title, its coordinator, the reservation period 2026-12-05 18:00 – 23:00, the four requirements in the order recorded with their quantities and technical requirements (and a note that "Lapel" must be confirmed), `can_reserve: true` and no notice.
- **Automated:** `test_tc_44_01_shows_the_requirements_and_the_reservation_period`

**TC-44-02 · Suitable equipment and how much can be reserved**
- **Traces to:** AC1, AC2 · **Type:** Positive · **Depends on:** A1, A5
- **Steps:** As hana, open R1.
- **Expected result:** Microphones: Shure 2 and Sennheiser 2, 0 reserved, 3 still needed, 4 can be reserved, *can reserve*. Projector: only BenQ is offered; Epson is excluded with "Lamp replacement". Speakers: only Bose is offered; JBL is excluded, quantity not recorded.
- **Automated:** `test_tc_44_02_shows_the_suitable_equipment_and_how_much_can_be_reserved`

**TC-44-03 · The coordinator can view but not reserve**
- **Traces to:** AC1 · **Type:** Positive · **Depends on:** A3
- **Steps:** As alice, open R1.
- **Expected result:** HTTP 200 with the four requirements and `can_reserve: false`.
- **Automated:** `test_tc_44_03_the_coordinator_can_view_but_not_reserve`

**TC-44-04 · Events that aren't approved can be viewed, not reserved for**
- **Traces to:** AC1 · **Type:** Negative · **Depends on:** A4
- **Steps:** As hana, open R4 (submitted) and R5 (cancelled).
- **Expected result:** `can_reserve: false`, with a notice saying equipment can only be reserved for approved events and naming the event's status.
- **Automated:** `test_tc_44_04_events_that_are_not_approved_can_be_viewed_but_not_reserved`

**TC-44-05 · Who may view, and in what order**
- **Traces to:** AC1 · **Type:** Negative (authorisation) · **Depends on:** A3, A13
- **Steps:** Open R1 with no token and with a deleted user's token; a missing event as hana; R1 as ben (another event's coordinator), dana, gus, admin and farah.
- **Expected result:** 401 (the second with "Your session is no longer valid"); 404; 403 without R1's title or requirements.
- **Automated:** `test_tc_44_05_who_may_view_and_in_what_order`

**TC-44-06 · An event with no requirements says so**
- **Traces to:** AC1 · **Type:** Positive (empty)
- **Steps:** As hana, open an approved event with no requirements.
- **Expected result:** No requirements and "No equipment requirements have been recorded for this event."
- **Automated:** `test_tc_44_06_an_event_with_no_requirements_says_so`

**TC-44-07 · A failed load is an error, not an empty page**
- **Traces to:** AC1 · **Type:** Negative (failure)
- **Steps:** Make reading the reservations fail and open R1.
- **Expected result:** HTTP 503, `retryable: true`, no internal error text, no requirements.
- **Automated:** `test_tc_44_07_a_failed_load_is_an_error_not_an_empty_page`

## AC2 + AC3 — Select equipment and quantities; the reservation is recorded and confirmed

**TC-44-08 · A reservation records the equipment, quantities, period and event**
- **Traces to:** AC2, AC3 · **Type:** Positive · **Depends on:** A1, A2
- **Steps:** As hana, reserve 2 × Shure and 1 × Sennheiser for R1's microphones.
- **Expected result:** HTTP 201, `saved: true`. Two reservations are recorded for R1 and its microphone requirement: Shure 2 and Sennheiser 1, each 2026-12-05 18:00 – 23:00, `reserved`, by hana, with when.
- **Automated:** `test_tc_44_08_a_reservation_records_the_equipment_quantities_period_and_event`

**TC-44-09 · The confirmation names what was reserved, for when, for which event**
- **Traces to:** AC3 · **Type:** Positive
- **Steps:** As TC-44-08.
- **Expected result:** The confirmation names "2 × Shure SLX-D", "1 × Sennheiser EW-D", the microphone requirement, Charity Gala and the period. The page that comes back shows the microphones 3 of 3 reserved, *fully reserved*, with both reservations and who made them.
- **Automated:** `test_tc_44_09_the_confirmation_names_the_equipment_quantities_period_and_event`

**TC-44-10 · Exactly the available quantity can be reserved, even if the requirement needs more**
- **Traces to:** AC2, AC5 · **Type:** Boundary · **Depends on:** A6
- **Steps:** Reserve 1 × Bose (all that is available) for R1's 2 speakers.
- **Expected result:** HTTP 201. Speakers: 1 reserved, 1 still needed, nothing more available, *none available*.
- **Automated:** `test_tc_44_10_exactly_the_available_quantity_can_be_reserved`

**TC-44-11 · More can be reserved later, up to what the requirement needs**
- **Traces to:** AC2 · **Type:** Positive · **Depends on:** A6
- **Steps:** Reserve 1 × Shure for R1's microphones, then 1 × Shure and 1 × Sennheiser.
- **Expected result:** 3 of 3 reserved, *fully reserved*; R1 has 2 Shure reserved and no more Shure to reserve.
- **Automated:** `test_tc_44_11_more_can_be_reserved_later_up_to_what_the_requirement_needs`

**TC-44-12 · A fully reserved requirement can't be reserved for again**
- **Traces to:** AC2 · **Type:** Negative · **Depends on:** A6
- **Steps:** Reserve 1 × BenQ for R1's projector, then try again.
- **Expected result:** HTTP 409 saying it is already fully reserved; still one reservation.
- **Automated:** `test_tc_44_12_a_fully_reserved_requirement_cannot_be_reserved_again`

**TC-44-13 · The selection is validated; a wrong one reserves nothing**
- **Traces to:** AC2 · **Type:** Negative (validation) · **Depends on:** A1, A6, A13
- **Steps:** Try to reserve for R1's microphones with: no items; items that aren't a list; quantity 0, 1.5, "2" or `true`; an item that doesn't exist; a projector; the Shure twice; and 2 + 2 microphones (4, when 3 are needed).
- **Expected result:** HTTP 422 each time, with `fields.items` saying what is wrong ("Select at least one…", "whole number", "was not found", "not suitable", "more than once", "no more than 3"). Nothing is reserved, nobody is notified.
- **Automated:** `test_tc_44_13_the_selection_is_validated_and_nothing_is_reserved_when_it_is_wrong`

**TC-44-14 · The requirement must be one of the event's**
- **Traces to:** AC2 · **Type:** Negative · **Depends on:** A13
- **Steps:** Reserve for R1 with `requirement_id` missing, "1" or `true`; then with a requirement that doesn't exist and with R2's requirement.
- **Expected result:** 422 naming `requirement_id`; then 404 "Equipment requirement not found." Nothing is reserved.
- **Automated:** `test_tc_44_14_the_requirement_must_be_one_of_the_events`

**TC-44-15 · Availability is checked again when reserving**
- **Traces to:** AC2, AC5 · **Type:** Business rule · **Depends on:** A7
- **Steps:** As hana, open R1 (2 Shure can be reserved). Then reserve 1 × Shure for R2 (overlapping). Then, from the page loaded before, reserve 2 × Shure for R1.
- **Expected result:** HTTP 409 with the shortfall: Shure, 2 requested, 1 available. Nothing is reserved for R1.
- **Automated:** `test_tc_44_15_availability_is_checked_again_when_reserving`

**TC-44-16 · Reserving locks the event, requirement and equipment before checking**
- **Traces to:** AC2 · **Type:** Business rule (concurrency) · **Depends on:** A7
- **Steps:** Reserve 1 × Shure for R1 and record the SQL sent.
- **Expected result:** The event, the requirement and the equipment rows are read `FOR UPDATE`, and the equipment is locked before the reservation is inserted.
- **Automated:** `test_tc_44_16_reserving_locks_the_event_requirement_and_equipment_first`

## AC4 — Reserved quantities are deducted for overlapping events

**TC-44-17 · An overlapping event can no longer reserve what was reserved**
- **Traces to:** AC4 · **Type:** Positive · **Depends on:** A5
- **Steps:** Reserve 2 × Shure for R1. As hana, open R2.
- **Expected result:** R2's Shure: 2 recorded, 2 reserved for other events, 0 to reserve; its microphones can still have the 2 Sennheisers.
- **Automated:** `test_tc_44_17_an_overlapping_event_can_no_longer_reserve_what_was_reserved`

**TC-44-18 · An event that only touches the period is not affected**
- **Traces to:** AC4 · **Type:** Boundary · **Depends on:** A5
- **Steps:** Reserve 2 × Shure for R1. Open R3 (starts at 23:00, when R1 ends).
- **Expected result:** R3 can still reserve 2 Shure.
- **Automated:** `test_tc_44_18_an_event_that_only_touches_the_period_is_not_affected`

**TC-44-19 · The availability check deducts reservations for overlapping events**
- **Traces to:** AC4 · **Type:** Positive · **Depends on:** A11
- **Steps:** Reserve 2 × Shure for R1. Check availability (SCRUM-43) for R2, R1 and R3.
- **Expected result:** R2: 2 microphones available, with the Shure shown as 2 recorded, 2 reserved for other events, 0 available. R1: still 4 (its own reservation counts for it). R3: 4.
- **Automated:** `test_tc_44_19_the_availability_check_deducts_reservations_for_overlapping_events`

**TC-44-20 · Reserving what another event holds is refused, with the available quantity**
- **Traces to:** AC4, AC5 · **Type:** Negative
- **Steps:** Reserve 2 × Shure for R2. Try to reserve 1 × Shure for R1.
- **Expected result:** HTTP 409: Shure 0 available; 2 can still be reserved for the requirement (the Sennheisers). Nothing is reserved for R1.
- **Automated:** `test_tc_44_20_reserving_what_another_event_holds_is_refused_with_the_available_quantity`

**TC-44-21 · Two requirements of one event can't reserve the same units**
- **Traces to:** AC4 · **Type:** Business rule · **Depends on:** A5
- **Steps:** Add 2 × Wireless microphone ("Handheld") to R1. Reserve 2 × Shure for the "Lapel" microphones, then try 1 × Shure for the "Handheld" ones.
- **Expected result:** HTTP 409: the Shure has 0 available.
- **Automated:** `test_tc_44_21_requirements_of_one_event_cannot_reserve_the_same_units_twice`

## AC5 + AC6 — More than available, or nothing suitable available

**TC-44-22 · More than available is refused, showing the available quantity**
- **Traces to:** AC5 · **Type:** Negative
- **Steps:** Reserve 2 × Bose for R1's speakers (1 is available).
- **Expected result:** HTTP 409: "Only 1 × Bose S1 is available for this event's period, not 2. Nothing was reserved.", with `shortfalls` (Bose, 2 requested, 1 available) and `available_quantity: 1`. Nothing is reserved; nobody is notified.
- **Automated:** `test_tc_44_22_more_than_available_is_refused_and_shows_the_available_quantity`

**TC-44-23 · One item over its availability stops the whole reservation**
- **Traces to:** AC5 · **Type:** Negative
- **Steps:** Reserve 1 × Sennheiser for R2. Reserve 1 × Shure and 2 × Sennheiser for R1.
- **Expected result:** HTTP 409 naming only the Sennheiser; the Shure isn't reserved either.
- **Automated:** `test_tc_44_23_one_item_over_its_availability_stops_the_whole_reservation`

**TC-44-24 · Unavailable equipment can't be reserved**
- **Traces to:** AC5 · **Type:** Negative · **Depends on:** A5
- **Steps:** Reserve 1 × Epson (in repair during R1) for R1's projector.
- **Expected result:** HTTP 409: the Epson has 0 available. Nothing is reserved.
- **Automated:** `test_tc_44_24_unavailable_equipment_cannot_be_reserved`

**TC-44-25 · No suitable equipment means no reservation**
- **Traces to:** AC6 · **Type:** Negative
- **Steps:** Open R1, then try to reserve a projector for its hologram projector.
- **Expected result:** The hologram projector is *none available*, "No suitable equipment is available to reserve", with no options. The attempt is refused (422: a projector is not suitable). Nothing is reserved.
- **Automated:** `test_tc_44_25_no_suitable_equipment_means_no_reservation`

**TC-44-26 · When every suitable item is taken, nothing can be reserved**
- **Traces to:** AC6 · **Type:** Negative · **Depends on:** A5
- **Steps:** R2 needs 4 microphones and reserves all four. Open R1, then try to reserve 1 × Shure for R1.
- **Expected result:** R1's microphones are *none available*, 0 to reserve; the attempt is refused with 409 "No suitable equipment is available…" and `available_quantity: 0`.
- **Automated:** `test_tc_44_26_when_every_suitable_item_is_taken_nothing_can_be_reserved`

## AC7 — A failed save confirms nothing and changes nothing

**TC-44-27 · A failed save confirms nothing and leaves the reservations as they were**
- **Traces to:** AC7 · **Type:** Negative (failure)
- **Steps:** Reserve 1 × BenQ for R1. Then make saving the reservation fail, and then saving the notification, and each time reserve 2 × Shure and 1 × Sennheiser for R1.
- **Expected result:** HTTP 503, `retryable: true`, "The equipment was not reserved, and the existing reservations are unchanged. Please try again.", no internal error text. R1 still has only the BenQ reservation, unchanged; no new notification; no email.
- **Automated:** `test_tc_44_27_a_failed_save_confirms_nothing_and_leaves_reservations_unchanged`

## AC8 — The coordinator is notified

**TC-44-28 · The coordinator is told what was reserved**
- **Traces to:** AC8 · **Type:** Positive · **Depends on:** A9
- **Steps:** Reserve 2 × Shure and 1 × Sennheiser for R1.
- **Expected result:** alice has one `equipment_reserved` notification for R1 naming both items with quantities, the requirement and the event; one email is queued to alice about Charity Gala with the same details; `notification: {"in_app": true, "email_queued": true}`. hana gets nothing.
- **Automated:** `test_tc_44_28_the_coordinator_is_told_what_was_reserved`

**TC-44-29 · An email queue failure doesn't undo the reservation**
- **Traces to:** AC8 · **Type:** Negative (failure) · **Depends on:** A9
- **Steps:** Make queuing the email fail and reserve 1 × BenQ for R1.
- **Expected result:** HTTP 201 with `email_queued: false`; the reservation and the in-app notification are saved.
- **Automated:** `test_tc_44_29_an_email_queue_failure_does_not_undo_the_reservation`

## AC9 — Cancelling, or changing the requirements, releases the reservation

Each case starts with R1 holding 2 × Shure and 1 × Sennheiser (microphones) and 1 × BenQ (projector).

**TC-44-30 · Cancelling the event releases its reservations**
- **Traces to:** AC9 · **Type:** Positive · **Depends on:** A10
- **Steps:** R2 can reserve 0 Shure. Set R1 to cancelled (there's no screen for it yet).
- **Expected result:** All three reservations are `released`, with when and "The event was cancelled."; R2 can reserve 2 Shure again; R1's page lists the three under released and none as current.
- **Automated:** `test_tc_44_30_cancelling_the_event_releases_its_reservations`

**TC-44-31 · Changing a requirement releases only its reservations**
- **Traces to:** AC9 · **Type:** Positive · **Depends on:** A10
- **Steps:** As alice, change R1's microphones from 3 to 4 (SCRUM-42 edit).
- **Expected result:** HTTP 200; the confirmation says its reserved equipment was released. The Shure and Sennheiser reservations are released with "The equipment requirement was changed."; the BenQ stays reserved; R2 can reserve 2 Shure again.
- **Automated:** `test_tc_44_31_changing_a_requirement_releases_only_its_reservations`

**TC-44-32 · Saving a requirement unchanged releases nothing**
- **Traces to:** AC9 · **Type:** Negative · **Depends on:** A10
- **Steps:** As alice, save R1's microphones with the same details.
- **Expected result:** HTTP 200; nothing is released.
- **Automated:** `test_tc_44_32_saving_a_requirement_unchanged_releases_nothing`

**TC-44-33 · Removing a requirement releases its reservations and keeps them as history**
- **Traces to:** AC9 · **Type:** Positive · **Depends on:** A10
- **Steps:** As alice, remove R1's microphones.
- **Expected result:** HTTP 200; the confirmation says its reserved equipment was released. The two reservations are kept as `released`, no longer linked to a requirement, with "The equipment requirement was removed."; R2 can reserve 2 Shure again.
- **Automated:** `test_tc_44_33_removing_a_requirement_releases_its_reservations_and_keeps_them_as_history`

**TC-44-34 · Changing the event's times releases its reservations**
- **Traces to:** AC9 · **Type:** Positive · **Depends on:** A10 *(Q9)*
- **Steps:** Change R1's start to 19:00.
- **Expected result:** All three are released with "The event's times were changed."
- **Automated:** `test_tc_44_34_changing_the_events_times_releases_its_reservations`

**TC-44-35 · Other changes to the event release nothing**
- **Traces to:** AC9 · **Type:** Negative · **Depends on:** A10
- **Steps:** Change R1's title and description.
- **Expected result:** All three are still reserved.
- **Automated:** `test_tc_44_35_other_changes_to_the_event_release_nothing`

## Who may reserve, and in what order

**TC-44-36 · Who may reserve, and in what order**
- **Traces to:** AC1, AC2 · **Type:** Negative (authorisation) · **Depends on:** A3, A13
- **Steps:** Reserve for R1 with no token and with a deleted user's token; for a missing event as hana; as alice, dana, gus, admin and farah; and as hana with a body that isn't JSON.
- **Expected result:** 401; 401; 404; 403 saying only Technical Support Staff can reserve; 400. Nothing is reserved.
- **Automated:** `test_tc_44_36_who_may_reserve_and_in_what_order`

**TC-44-37 · Only approved events can have equipment reserved**
- **Traces to:** AC1 · **Type:** Negative · **Depends on:** A4
- **Steps:** As hana, reserve 1 × Shure for R4 (submitted) and R5 (cancelled).
- **Expected result:** HTTP 409 naming the status; nothing is reserved.
- **Automated:** `test_tc_44_37_only_approved_events_can_be_reserved_for`

## The rules without a database (`test_equipment_reservation_unit.py`)

The same rules on plain objects: the availability check deducts other events' reservations from each item and never goes below 0 (A5, A11); an event's own reservations are taken off what it can still reserve (A5); a requirement is *fully reserved* when nothing more is needed, otherwise *none available* when nothing can be reserved, otherwise *can reserve* (A6); a selection needs whole quantities from 1 to 1000, items that exist and suit the requirement, each once, and no more than the requirement still needs (A6); only items asked for beyond what is available are shortfalls, and the message shows the available quantity (AC5). **Automated:** `DeductionRuleTests`, `OptionRuleTests`, `SelectionRuleTests`.

## Frontend

`EquipmentReservationPage` (`/events/:eventId/equipment-reservations`), linked from the equipment requirements page ("Reserve equipment" for Technical Support Staff, "Reserved equipment" for the coordinator) and from the availability check.

**TC-44-38 · The page shows the reservation period, each requirement and what can be reserved** — AC1 · `shows the reservation period and what can be reserved for each requirement`

**TC-44-39 · Reserving sends the chosen quantities and shows the confirmation** — AC2, AC3 · `reserves the chosen quantities and shows the confirmation`

**TC-44-40 · More than available shows the available quantity and keeps the selection** — AC5 · `shows the available quantity when more is chosen than is available`

**TC-44-41 · No suitable equipment: no form, and it says so** — AC6 · `says when no suitable equipment is available and offers nothing to reserve`

**TC-44-42 · A failed save explains itself and keeps the selection for a retry** — AC7 · `keeps the selection after a failed save so it can be tried again`

**TC-44-43 · The coordinator sees the reservations but can't reserve** — AC1, AC8 · `shows the coordinator the reservations without a way to reserve`

**TC-44-44 · Released reservations are listed with why** — AC9 · `lists released reservations with the reason`

**TC-44-45 · Events that aren't approved say why nothing can be reserved** — AC1 · `explains why an event that is not approved cannot be reserved for`

**TC-44-46 · Moving to another event shows only that event** — AC1 · `shows only the event in the address, even when the previous event's page arrives last`

**TC-44-47 · Technical Support reach it from the equipment requirements page; the coordinator gets a view link** — AC1 · `EquipmentRequirementsPage` "links Technical Support Staff to reserving equipment" and "links the coordinator to the reserved equipment"

**TC-44-48 · The availability check shows what other events have reserved** — AC4 · `EquipmentAvailabilityPage` "shows how much of each item other events have reserved"

Also: `explains a failed load and offers Retry`.

---

## Traceability matrix

| AC | Test cases |
|----|------------|
| AC1 | 01, 02, 03, 04, 05, 06, 07, 36, 37, 38, 43, 45, 46, 47 |
| AC2 | 02, 08, 10, 11, 12, 13, 14, 15, 16, 36, 39 |
| AC3 | 08, 09, 39 |
| AC4 | 17, 18, 19, 20, 21, 48 |
| AC5 | 10, 15, 20, 22, 23, 24, 40 |
| AC6 | 25, 26, 41 |
| AC7 | 27, 42 |
| AC8 | 28, 29, 43 |
| AC9 | 30, 31, 32, 33, 34, 35, 44 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Is reserving by item and quantity right, or should individual units (serial numbers) be reserved? | A1 |
| Q2 | Does equipment need setup or return time around the event, so the reservation period is longer than the event? | A2, TC-44-18 |
| Q3 | Should the event's coordinator also be able to reserve, or only view? | A3, TC-44-03 |
| Q4 | Should equipment be reservable before an event is approved (e.g. submitted or under review)? | A4, TC-44-37 |
| Q5 | What makes two overlapping events "compatible", so they could share the same equipment (for example two sessions of one event in the same room)? As built, any other overlapping event's reservations are deducted. | A5, AC4 |
| Q6 | May part of a requirement be reserved (as built), or must a reservation cover the whole quantity? | A6, TC-44-10 |
| Q7 | Should reserving record that the technical requirements were checked, e.g. a tick box or note? | A8 |
| Q8 | Should anyone (the Technical Support Staff member who reserved, the coordinator) be told when a reservation is released? | A10 |
| Q9 | Should a change to the event's times release its reservations (as built), or move them to the new times when the equipment is still available? | A10, TC-44-34 |
| Q10 | Should reserving change the requirement's arrangement status, e.g. to a new "Reserved" status? | A12 |
