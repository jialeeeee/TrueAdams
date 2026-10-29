# SCRUM-42 — Record Equipment Requirements for an Event: Test Cases

**User story:** As an Event Coordinator, I want to record an event's equipment requirements so that Technical Support Staff can assess what needs to be arranged.

**Created:** 21 Oct 2026 · **Status of all cases:** automated cases pass (21 Oct 2026, Supabase + Vitest); end-to-end check passed in the browser, see [the DoD evidence](../evidence/SCRUM-42-dod-evidence.md) · **Automated tests:** `backend/tests/test_equipment_requirements.py`, `frontend/src/pages/EquipmentRequirementsPage.test.jsx`, `frontend/src/pages/EquipmentRequestsPage.test.jsx` (+ the link in `EventPlanningPage.test.jsx`) · **Endpoints:** `GET/POST /api/events/<id>/equipment-requirements`, `PUT/DELETE /api/events/<id>/equipment-requirements/<requirement_id>`, `PATCH /api/events/<id>/equipment-requirements/<requirement_id>/arrangement`, `GET /api/events/equipment-requests` · **Related:** SCRUM-29 (the organiser's free-text equipment note), SCRUM-53 (says equipment requirements are recorded here, not through the planning edit), SCRUM-43 (checks availability against these requirements), SCRUM-44 (reserves equipment for them), SCRUM-46 (the organiser asks to change them)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The coordinator can select an event they are authorised to coordinate and enter equipment types, quantities, and relevant technical requirements. |
| AC2 | Invalid equipment requirements are identified and are not saved until corrected. |
| AC3 | Successful saving records the requirements against the selected event, and the saved requirements can subsequently be viewed. |
| AC4 | Technical Support Staff can view the requirements and update the request as arrangements are made. |
| AC5 | Recording an equipment requirement does not itself reserve equipment or reduce the quantity considered available. |
| AC6 | A requirement can remain recorded even when suitable equipment is unavailable; it is not represented as fulfilled or reserved. |
| AC7 | If saving fails, existing recorded requirements remain unchanged and the Event Coordinator is informed. |

## Working assumptions (to confirm)

- **A1 — One record per item:** each requirement is a row in a new `equipment_requirements` table (`db/equipment_requirements.sql`): equipment type, quantity, technical requirements, arrangement status and Technical Support's note, with who recorded or updated it and when (naive UTC). The coordinator adds, edits and removes one requirement at a time, so a failed save can only ever affect that one.
- **A2 — The organiser's note is kept:** `Event.equipment_requirements` (the organiser's free text from SCRUM-29) is not changed or migrated. The equipment page shows it read-only as "From the organiser's request" so the coordinator can turn it into recorded requirements. *(Q5)*
- **A3 — Who records:** only the event's current coordinator, while their role is still `coordinator` (as SCRUM-34/53). *(Q1)*
- **A4 — Which events:** any event with a coordinator, except `cancelled` and `rejected` ones (HTTP 409). Their requirements can still be viewed. Drafts never have a coordinator. *(Q2)*
- **A5 — What is valid:** checked in full before anything is saved, with every invalid field named at once (HTTP 422, `fields`):
  - equipment type: required text, 1–100 characters after spaces are collapsed;
  - quantity: a whole number from 1 to `EQUIPMENT_QUANTITY_MAX` = 1,000 (not text, not a decimal, not true/false) *(Q3)*;
  - technical requirements: optional text, up to 1,000 characters; blank means none recorded;
  - the same type with the same technical requirements (ignoring case and spacing) can't be recorded twice for one event: the coordinator is told to change the existing one's quantity.
- **A6 — Types are free text,** not chosen from the equipment catalogue, so a requirement can be recorded even when no suitable equipment exists (AC6). SCRUM-43 will match a type to equipment ignoring case and spacing. *(Q4)*
- **A7 — Technical Support Staff:** any `tech_staff` user can see every open event that has requirements, view them, and set each requirement's arrangement status with an optional note (up to 1,000 characters). The statuses are **Requested** (the starting status), **Being arranged** and **Suitable equipment unavailable**. Nobody can set a requirement to reserved or fulfilled here: reserving is SCRUM-44. They cannot change the coordinator's details. Since SCRUM-97, the page shows who made the latest update and when, an update that changes nothing keeps the earlier who and when, an update is refused (409) if the coordinator changed the requirement after it was opened, and a failed update says the recorded requirements are unchanged (SCRUM-97 A3 to A8). *(Q6)*
- **A8 — Editing resets the arrangement:** when the coordinator changes a requirement's type, quantity or technical requirements, its status goes back to Requested and Technical Support's note, and who updated it and when, are cleared, because the arrangements were for the old details (changed after the review of PR #47: keeping the note made the old arrangement look as if it applied to the new details). Saving with nothing changed keeps everything. Removing a requirement deletes it. Since SCRUM-44, changing or removing a requirement also releases any equipment reserved for it, and the confirmation says so (SCRUM-44 A10, TC-44-31 to 33). *(Q7)*
- **A9 — Who can view:** the event's coordinator and Technical Support Staff. Everyone else, including the organiser and other coordinators, is refused (HTTP 403) without the event's details. Since SCRUM-96, a draft's requirements are "Event not found." (HTTP 404) for everyone, as an unknown ID is (SCRUM-96 A3, TC-96-05). *(Q8)*
- **A10 — No notifications** are sent when requirements are recorded or updated. *(Q9)*
- **A11 — Order of checks:** 401 (no valid user) → 404 (no such event) → 403 (not allowed) → 404 (no such requirement on this event) → 409 (cancelled or rejected event) → 400 (body is not a JSON object) → 422 (invalid fields). The requirement's 404 comes after the 403 so people who may not see an event learn nothing about its requirements. The 409 comes before validation, as in the planning edit (SCRUM-53).
- **A12 — Failures:** a failed load is an error (HTTP 503, `retryable: true`), never an empty list. A failed save, edit, removal or status update is rolled back, leaves every recorded requirement as it was, and says so (HTTP 503, `retryable: true`). The page keeps what was entered. Once a change is committed it is never reported as failed: if reading the updated list back fails, the reply is the usual success with `saved: true` and `refresh_error` instead of the list, and the page loads the list again (added after the review of PR #47). The page shows only the event in its address, and only the newest reply.

## Seed data (EQ-SEED)

Users: `USERS` and `LEADS` from `backend/tests/seed_data.py`: alice and ben (coordinators), chloe (coordinator with no events), dana and evan (organisers), farah (attendee), gus (venue staff), hana (tech staff), admin and lena (Coordinator Lead).

| Key | Event | Status | Organiser | Coordinator | Start – end (Singapore time) | Organiser's equipment note |
|-----|-------|--------|-----------|-------------|------------------------------|----------------------------|
| G1 | Charity Gala | approved | dana | alice | 2026-12-05 18:00 – 23:00 | "Two wireless microphones and a projector" |
| G2 | Product Launch | submitted | evan | ben | 2026-11-20 14:00 – 16:00 | none |
| G3 | Spring Fair | cancelled | dana | alice | 2026-11-01 10:00 – 16:00 | none |
| G4 | Winter Fest | rejected | dana | alice | 2026-12-20 10:00 – 16:00 | none |
| G5 | Tech Talk | under_review | dana | alice | 2026-11-15 09:00 – 11:00 | none |

Equipment: "Shure SLX-D", category "Wireless microphone", 4 available.

The requirement used is **2 × Wireless microphone**, technical requirements "Lapel, with spare batteries".

---

## AC1 — The coordinator enters equipment requirements for their event

**TC-42-01 · Record a requirement with type, quantity and technical requirements**
- **Traces to:** AC1, AC3 · **Type:** Positive
- **Steps:** As alice, record "  Wireless   microphone " × 2 with " Lapel, with spare batteries " for G1.
- **Expected result:** HTTP 201. The saved requirement belongs to G1 and reads "Wireless microphone", 2, "Lapel, with spare batteries", status Requested, recorded by alice. The confirmation names the requirement.
- **Automated:** `test_tc_42_01_records_type_quantity_and_technical_requirements`

**TC-42-02 · Technical requirements are optional**
- **Traces to:** AC1 · **Type:** Positive
- **Steps:** As alice, record "Projector" × 1 for G1 with no technical requirements, then "Screen" × 1 with only spaces.
- **Expected result:** HTTP 201 each time, with technical requirements not recorded (null).
- **Automated:** `test_tc_42_02_technical_requirements_are_optional`

**TC-42-03 · Several requirements for one event, in the order recorded**
- **Traces to:** AC1, AC3 · **Type:** Positive
- **Steps:** As alice, record Wireless microphone × 2, Projector × 1 and Wireless microphone × 1 ("Handheld") for G1, then view G1's requirements.
- **Expected result:** All three are listed in that order. The same type with different technical requirements is allowed.
- **Automated:** `test_tc_42_03_several_requirements_listed_in_the_order_recorded`

**TC-42-04 · Only the event's coordinator can record, edit or remove**
- **Traces to:** AC1 · **Type:** Negative (authorisation) · **Depends on:** A3
- **Steps:** Try to record a requirement for G1 as ben, chloe, dana (its organiser), hana (tech staff), gus, farah, admin and lena. Then try to edit and remove a requirement alice recorded, as ben and hana.
- **Expected result:** HTTP 403 each time, with no event details in the message. Nothing is recorded or changed.
- **Automated:** `test_tc_42_04_only_the_events_coordinator_can_record_edit_or_remove`

**TC-42-05 · The coordinator can correct and remove a requirement**
- **Traces to:** AC1, AC3 · **Type:** Positive · **Depends on:** A8
- **Steps:** As alice, record Wireless microphone × 2 for G1. Change it to × 3 with "Handheld". Then remove it.
- **Expected result:** The edit returns HTTP 200 and the list shows × 3, "Handheld". The removal returns HTTP 200 and the list is empty.
- **Automated:** `test_tc_42_05_the_coordinator_can_edit_and_remove_a_requirement`

**TC-42-06 · Editing the details sends a requirement back to Requested**
- **Traces to:** AC1, AC4 · **Type:** Business rule · **Depends on:** A8
- **Steps:** hana sets alice's Wireless microphone × 2 to Being arranged. alice saves it unchanged, then changes the quantity to 3.
- **Expected result:** The unchanged save keeps Being arranged, hana's note and that hana updated it. The quantity change sets it back to Requested and clears the note and who updated it and when; the message says why.
- **Automated:** `test_tc_42_06_editing_the_details_sends_it_back_to_requested`

**TC-42-07 · Cancelled and rejected events can't be changed**
- **Traces to:** AC1 · **Type:** Negative (business rule) · **Depends on:** A4
- **Steps:** As alice, record a requirement for G3 (cancelled) and G4 (rejected). Record one for G5 (under review).
- **Expected result:** G3 and G4 → HTTP 409 naming the status, nothing saved. G5 → HTTP 201.
- **Automated:** `test_tc_42_07_cancelled_and_rejected_events_cannot_be_changed`

**TC-42-08 · Signed-out users, unknown events and other events' requirements**
- **Traces to:** AC1 · **Type:** Negative
- **Steps:** Call each endpoint without a token and with the token of a deleted user. As alice, record for a missing event ID. As alice, edit G1's requirement through G2's URL, and an unknown requirement ID.
- **Expected result:** HTTP 401 with "Your session is no longer valid. Please log in again."; HTTP 404 "Event not found."; HTTP 404 "Equipment requirement not found." for both, with nothing changed.
- **Automated:** `test_tc_42_08_signed_out_unknown_event_and_other_events_requirement`

## AC2 — Invalid requirements are identified and not saved

**TC-42-09 · Equipment type is required and limited to 100 characters**
- **Traces to:** AC2 · **Type:** Boundary · **Depends on:** A5
- **Steps:** As alice, record for G1 with the type missing, null, "", "   ", 42, 101 characters, then exactly 100 characters.
- **Expected result:** HTTP 422 with `fields.equipment_type` for each invalid one; 100 characters → HTTP 201.
- **Automated:** `test_tc_42_09_equipment_type_is_required_and_at_most_100_characters`

**TC-42-10 · Quantity must be a whole number from 1 to 1,000**
- **Traces to:** AC2 · **Type:** Boundary · **Depends on:** A5
- **Steps:** As alice, record for G1 with quantity missing, null, 0, -1, 1.5, "2", true and 1001, then 1 and 1000.
- **Expected result:** HTTP 422 with `fields.quantity` for each invalid one; 1 and 1000 → HTTP 201.
- **Automated:** `test_tc_42_10_quantity_must_be_a_whole_number_from_1_to_1000`

**TC-42-11 · Technical requirements must be text of up to 1,000 characters**
- **Traces to:** AC2 · **Type:** Boundary · **Depends on:** A5
- **Steps:** As alice, record for G1 with technical requirements 5, ["a"] and 1,001 characters, then exactly 1,000.
- **Expected result:** HTTP 422 with `fields.technical_requirements` for each invalid one; 1,000 → HTTP 201.
- **Automated:** `test_tc_42_11_technical_requirements_must_be_text_up_to_1000_characters`

**TC-42-12 · Every problem is named at once, nothing is saved, and the corrected entry saves**
- **Traces to:** AC2, AC3 · **Type:** Negative then positive
- **Steps:** As alice, record for G1 with type "", quantity 0 and technical requirements 7. Then send the corrected values.
- **Expected result:** HTTP 422 naming all three fields; G1 still has no requirements. The corrected entry → HTTP 201.
- **Automated:** `test_tc_42_12_every_problem_is_named_and_the_corrected_entry_saves`

**TC-42-13 · The same requirement can't be recorded twice**
- **Traces to:** AC2 · **Type:** Negative · **Depends on:** A5
- **Steps:** As alice, record Wireless microphone × 2 "Lapel, with spare batteries" for G1, then "wireless MICROPHONE" × 1 "lapel,  with spare batteries". Also edit a second requirement so that it duplicates the first.
- **Expected result:** HTTP 422 with `fields.equipment_type` telling her to change the existing one's quantity. Only the first requirement is recorded, and the edited one is unchanged.
- **Automated:** `test_tc_42_13_the_same_requirement_cannot_be_recorded_twice`

**TC-42-14 · An invalid edit leaves the requirement unchanged**
- **Traces to:** AC2, AC7 · **Type:** Negative
- **Steps:** As alice, edit G1's Wireless microphone × 2 to quantity -3.
- **Expected result:** HTTP 422 with `fields.quantity`; the requirement is still × 2.
- **Automated:** `test_tc_42_14_an_invalid_edit_leaves_the_requirement_unchanged`

**TC-42-15 · The body must be a JSON object**
- **Traces to:** AC2 · **Type:** Negative
- **Steps:** As alice, record for G1 with no body, a list and a string.
- **Expected result:** HTTP 400 "Send the equipment requirement as a JSON object." Nothing saved.
- **Automated:** `test_tc_42_15_the_body_must_be_a_json_object`

## AC3 — Saved requirements are recorded against the event and can be viewed

**TC-42-16 · Saved requirements are shown when the page is opened again**
- **Traces to:** AC3 · **Type:** Positive
- **Steps:** As alice, record Wireless microphone × 2 for G1. Load G1's requirements with a new token.
- **Expected result:** HTTP 200 with the event (title, status, times, coordinator), the organiser's note "Two wireless microphones and a projector", and the requirement as saved with its status label "Requested". G2's list does not include it.
- **Automated:** `test_tc_42_16_saved_requirements_are_shown_against_the_event`

**TC-42-17 · An event with no requirements says so**
- **Traces to:** AC3 · **Type:** Positive (empty)
- **Steps:** As alice, load G5's requirements.
- **Expected result:** An empty list and "No equipment requirements have been recorded for this event."; `message` is null when there are requirements.
- **Automated:** `test_tc_42_17_an_event_with_no_requirements_says_so`

**TC-42-18 · Cancelled and rejected events can be viewed, not changed**
- **Traces to:** AC3 · **Type:** Positive · **Depends on:** A4
- **Steps:** Record a requirement against G3 directly, then load it as alice and as hana.
- **Expected result:** HTTP 200 with the requirement, `can_edit` and `can_update_arrangements` false, and a notice that the event is cancelled.
- **Automated:** `test_tc_42_18_cancelled_events_can_be_viewed_but_not_changed`

## AC4 — Technical Support Staff view and update the requirements

**TC-42-19 · Technical Support Staff can view any event's requirements**
- **Traces to:** AC4 · **Type:** Positive · **Depends on:** A7
- **Steps:** As hana, load G1's requirements (G1 is not related to her in any way).
- **Expected result:** HTTP 200 with the requirements; `can_update_arrangements` true and `can_edit` false. For alice it is the other way round.
- **Automated:** `test_tc_42_19_technical_support_can_view_any_events_requirements`

**TC-42-20 · Technical Support Staff see which events need equipment arranged**
- **Traces to:** AC4 · **Type:** Positive · **Depends on:** A7
- **Steps:** Record requirements for G1 (two: one Requested, one Being arranged), G2 (one), and directly against G3 (cancelled). As hana, load the equipment requests list.
- **Expected result:** G2 then G1 (soonest first), each with its coordinator, requirement count and count per status. G3, G4 and G5 are not listed. (With nothing to arrange the list says "No events have equipment requirements to arrange."; real data may be present, so that is checked on the page, TC-42-38.)
- **Automated:** `test_tc_42_20_technical_support_see_which_events_need_equipment`

**TC-42-21 · Technical Support Staff update a requirement as arrangements are made**
- **Traces to:** AC4 · **Type:** Positive · **Depends on:** A7
- **Steps:** As hana, set G1's Wireless microphone to Being arranged with the note "Two lapel mics held at the AV store". Load the requirements as alice.
- **Expected result:** HTTP 200. alice sees "Being arranged", the note, and that hana updated it and when. The type, quantity and technical requirements are unchanged.
- **Automated:** `test_tc_42_21_technical_support_update_the_arrangement`

**TC-42-22 · Only valid arrangement statuses are accepted**
- **Traces to:** AC4, AC6 · **Type:** Negative · **Depends on:** A7
- **Steps:** As hana, set the status to "reserved", "fulfilled", "done", "", null and 3, and the note to 1,001 characters.
- **Expected result:** HTTP 422 with `fields.status` or `fields.note`; the requirement stays Requested.
- **Automated:** `test_tc_42_22_only_valid_arrangement_statuses_are_accepted`

**TC-42-23 · Only Technical Support Staff can view the list or update arrangements; others can't view**
- **Traces to:** AC4 · **Type:** Negative (authorisation) · **Depends on:** A7, A9
- **Steps:** Update the arrangement as alice, ben, dana, gus, admin and lena. Load the equipment requests list as alice. Load G1's requirements as ben, chloe, dana, evan, farah, gus, admin and lena.
- **Expected result:** HTTP 403 each time, with no requirement or event details; nothing changes.
- **Automated:** `test_tc_42_23_only_technical_support_update_and_others_cannot_view`

## AC5 — Recording does not reserve equipment

**TC-42-24 · Recording, editing and removing never touch equipment availability**
- **Traces to:** AC5 · **Type:** Business rule
- **Steps:** With "Shure SLX-D" (Wireless microphone, 4 available), alice records Wireless microphone × 2 for G1, changes it to × 3, and hana marks it Being arranged.
- **Expected result:** The equipment still shows 4 available. The confirmation says nothing has been reserved; no response says reserved, fulfilled or confirmed.
- **Automated:** `test_tc_42_24_recording_does_not_reserve_or_reduce_availability`

## AC6 — A requirement stays recorded when equipment is unavailable

**TC-42-25 · A requirement with no suitable equipment can be recorded**
- **Traces to:** AC6 · **Type:** Positive · **Depends on:** A6
- **Steps:** As alice, record "Hologram projector" × 1 for G1 (no such equipment exists).
- **Expected result:** HTTP 201, status Requested.
- **Automated:** `test_tc_42_25_a_requirement_with_no_suitable_equipment_can_be_recorded`

**TC-42-26 · Marked unavailable, it stays recorded and is not shown as fulfilled**
- **Traces to:** AC6 · **Type:** Positive · **Depends on:** A7
- **Steps:** As hana, set "Hologram projector" to Suitable equipment unavailable with a note. Load the requirements as alice.
- **Expected result:** The requirement is still listed with status "unavailable" and the label "Suitable equipment unavailable"; nothing says reserved or fulfilled.
- **Automated:** `test_tc_42_26_unavailable_stays_recorded_and_is_not_fulfilled`

## AC7 — A failed save changes nothing and says so

**TC-42-27 · A failed save keeps the existing requirements and can be retried**
- **Traces to:** AC7 · **Type:** Negative (failure)
- **Steps:** alice has Wireless microphone × 2 for G1. Make the commit fail while she records Projector × 1, while she changes the microphones to × 3, and while she removes them.
- **Expected result:** HTTP 503, `retryable: true`, a message saying the existing requirements are unchanged, no internal error text. G1 still has exactly Wireless microphone × 2. Recording Projector again then succeeds.
- **Automated:** `test_tc_42_27_a_failed_save_keeps_existing_requirements`

**TC-42-28 · A failed arrangement update changes nothing**
- **Traces to:** AC7, AC4 · **Type:** Negative (failure)
- **Steps:** Make the commit fail while hana sets the microphones to Being arranged.
- **Expected result:** HTTP 503, `retryable: true`; still Requested, with no note.
- **Automated:** `test_tc_42_28_a_failed_arrangement_update_changes_nothing`

**TC-42-29 · A failed load is reported as a failure, not an empty list**
- **Traces to:** AC7, AC3 · **Type:** Negative (failure) · **Depends on:** A12
- **Steps:** Make the database fail while alice loads G1's requirements and while hana loads the equipment requests list.
- **Expected result:** HTTP 503, `retryable: true`, and no `requirements` or `events` in the reply.
- **Automated:** `test_tc_42_29_a_failed_load_is_a_failure_not_an_empty_list`

**TC-42-40 · A failure after the change is saved is not reported as a failed save** *(added after the review of PR #47)*
- **Traces to:** AC7 · **Type:** Negative (failure) · **Depends on:** A12
- **Steps:** Make reading the updated list fail after the commit, while alice records a Projector, changes the microphones to 3 and removes them, and while hana marks them Being arranged.
- **Expected result:** Each reply is the usual success (201 or 200) with the confirmation, `saved: true` and a `refresh_error` saying the change was saved; never an `error` or "unchanged". Each change is in the database.
- **Automated:** `test_tc_42_40_a_failure_after_saving_is_not_reported_as_a_failed_save`

## Frontend

`EquipmentRequirementsPage` (`/events/:eventId/equipment`, linked from the coordinator's planning page) and `EquipmentRequestsPage` (`/equipment-requests`, in the navigation for Technical Support Staff). The API is mocked with replies that mirror the backend contract.

**TC-42-30 · The coordinator sees the event, the organiser's note and the requirements** — AC1, AC3 · `shows the event, the organiser's note and the recorded requirements`

**TC-42-31 · The coordinator records a requirement and sees the confirmation** — AC1, AC3, AC5 · `records a requirement and shows the confirmation`

**TC-42-32 · Invalid entries are named next to their fields and what was entered stays** — AC2 · `shows each invalid field and keeps what was entered`

**TC-42-33 · A failed save says the existing requirements are unchanged and keeps the entry** — AC7 · `keeps the entry when saving fails so it can be saved again`

**TC-42-34 · The coordinator edits and removes a requirement** — AC1 · `edits a requirement`, `cancels an edit without saving` and `removes a requirement`

**TC-42-35 · Technical Support Staff update the arrangement status, with no record or edit form** — AC4, AC6 · `lets Technical Support Staff update the arrangement status`

**TC-42-36 · A cancelled event is read-only, with its notice** — AC1 · `shows a cancelled event's requirements read-only`

**TC-42-37 · A load failure offers Retry; a refusal does not** — AC7 · `offers Retry after a load failure` and `shows a refusal without Retry`

**TC-42-38 · Technical Support Staff see the events that need equipment, each linking to its requirements; an empty list says so, and a failed load is never shown as empty** — AC4, AC7 · `EquipmentRequestsPage` tests

**TC-42-39 · The planning page links to the equipment requirements** — AC1 · `EventPlanningPage` "links to the equipment requirements"

**TC-42-41 · Moving to another event shows only that event** *(added after the review of PR #47)* — AC3 · `shows only the event in the address, even when the previous event's reply arrives last`, `starts the next event with an empty form, not the previous event's edit`, `ignores a save for the previous event that finishes after moving on`, `keeps the newest list when an older load arrives after a save`

**TC-42-42 · A change saved without its list coming back is reloaded, and still said to be saved** *(added after the review of PR #47)* — AC7 · `loads the list again when the change was saved but the list could not be sent back`, `says the change was saved when the list can't be loaded afterwards either`

---

## Traceability matrix

| AC | Test cases |
|----|------------|
| AC1 | 01, 02, 03, 04, 05, 06, 07, 08, 30, 31, 34, 36, 39 |
| AC2 | 09, 10, 11, 12, 13, 14, 15, 32 |
| AC3 | 01, 03, 05, 12, 16, 17, 18, 29, 30, 31, 41 |
| AC4 | 06, 19, 20, 21, 22, 23, 28, 35, 38 |
| AC5 | 24, 31 |
| AC6 | 22, 25, 26, 35 |
| AC7 | 14, 27, 28, 29, 33, 37, 38, 40, 42 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Should only the event's assigned coordinator record its equipment requirements (as built), or also the Coordinator Lead? | A3, TC-42-04 |
| Q2 | Should requirements be editable for every active status (as built), or only once the event is approved? Should cancelled and rejected events be locked (as built)? | A4, TC-42-07 |
| Q3 | Is 1,000 the right maximum quantity for one requirement? | A5, TC-42-10 |
| Q4 | Should equipment types be chosen from a defined list rather than typed freely? A defined list makes availability matching (SCRUM-43) exact, but then nothing outside the list could be recorded. | A6, TC-42-25 |
| Q5 | Should the organiser's free-text equipment note from the request be kept alongside the recorded requirements (as built), or replaced by them? | A2 |
| Q6 | What does Technical Support "update the request" with? Assumed: a status (Requested, Being arranged, Suitable equipment unavailable) and a note. | A7, TC-42-21, 22 |
| Q7 | When the coordinator changes a requirement that Technical Support are already arranging, should it go back to Requested with Technical Support's note cleared (as built), or should the earlier arrangement be kept as history? | A8, TC-42-06 |
| Q8 | Should the organiser or the Coordinator Lead be able to view the recorded requirements? | A9, TC-42-23 |
| Q9 | Should Technical Support Staff be notified when requirements are recorded or changed, or the coordinator when an arrangement is updated? | A10 |
