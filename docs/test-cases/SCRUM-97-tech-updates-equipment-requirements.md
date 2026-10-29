# SCRUM-97 — Technical Support Updates an Event's Equipment Requirements: Test Cases

**User story:** As a Technical Support Staff member, I want to update an event's equipment requirements as arrangements are made, so that the record shows what has been arranged.

**Created:** 30 Oct 2026 · **Status of all cases:** written test-first; not yet passing · **Automated tests:** `backend/tests/test_tech_updates_equipment.py`, `frontend/src/pages/EquipmentRequirementsPage.test.jsx` (the "SCRUM-97" block) · **Endpoint:** `PATCH /api/events/<id>/equipment-requirements/<requirement_id>/arrangement` (built by SCRUM-42) · **Related:** SCRUM-42 (records the requirements and first let Technical Support update the arrangement: AC4, TC-42-21 to 23, 28), SCRUM-96 (Technical Support view the requirements on the same page), SCRUM-44 (reserving equipment, which is not done here)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | I can update a requirement as arrangements are made, and the update is saved with who and when. |
| AC2 | Only Technical Support Staff can update. Anyone else is denied and nothing changes. |
| AC3 | If saving fails, the existing requirements are unchanged and an error is shown. |

## Working assumptions (to confirm)

- **A1 — Built on SCRUM-42:** the endpoint, its statuses and the arrangement form on `/events/:eventId/equipment` already exist from SCRUM-42 AC4. This story checks them from Technical Support's side and adds what was missing (A3 to A6). No new table or field.
- **A2 — What "update a requirement" means:** Technical Support set a requirement's **arrangement status** (Requested, Being arranged or Suitable equipment unavailable) and an optional **note** of up to 1,000 characters. They don't change the coordinator's details (type, quantity, technical requirements), and nothing here reserves equipment: that is SCRUM-44 (SCRUM-42 A7). *(Q1)*
- **A3 — Who and when, shown:** every saved update stores who made it and when (naive UTC), replacing the previous one, and the page now shows it under the requirement: "Arrangement updated by <email> on <date and time>", in the viewer's local time like other saved times. Only the latest update is kept, not a history. *(Q2)*
- **A4 — An update that changes nothing:** sending the status and note already recorded saves nothing, keeps the earlier who and when, and says "No changes were made to the arrangement for 2 × Wireless microphone." Otherwise pressing Update would make someone look responsible for an arrangement they didn't touch. *(Q2)*
- **A5 — The update is for the details Technical Support saw:** the page sends the requirement's `last_saved_at` with the update. If the coordinator has changed the requirement since (SCRUM-42 A8 then sends it back to Requested), the update is refused with HTTP 409 and `reload: true`: "The coordinator has changed this requirement since you opened it, so your update was not saved. It is now 5 × Wireless microphone: check the new details and update it again." Nothing changes, and the page reloads to show the new details. The row is locked while it is checked and saved, so an update and the coordinator's edit can't interleave. Without `last_saved_at` (older clients) the update is checked as before. Two Technical Support members updating the same requirement: the later update wins, and its who and when are shown. *(Q3)*
- **A6 — Drafts:** a draft is "Event not found." (HTTP 404) to everyone, as SCRUM-96 does for viewing; a draft never has requirements anyway.
- **A7 — Denied, and nothing changes:** anyone but Technical Support Staff, including the event's own coordinator, gets HTTP 403 "Only Technical Support Staff can update equipment arrangements." with no event or requirement details. The requirement, its who and when, and the event are unchanged, and no notification or email is sent. The role is read from the database on every request. Checks run 401 → 404 (event) → 403 → 404 (requirement) → 409 (cancelled or rejected event) → 400/422 → 409 (changed since opened). The requirement is looked up after the permission check, so people who may not update learn nothing about requirements (SCRUM-42 A11).
- **A8 — A failed save:** HTTP 503 `retryable: true`, "The arrangement was not saved, and the recorded requirements are unchanged. Please try again." (was "The arrangement status was not saved. Please try again."). Every requirement stays exactly as it was. The page shows the message (or, with no reply, "…Check your connection and try again."), keeps the shown requirements and what was chosen and typed in the form, so pressing Update again retries. *(Q4)*
- **A9 — Notifications:** none, as in SCRUM-42 (its open question Q9).

## Seed data (TU-SEED)

EQ-SEED from SCRUM-42 (users `USERS` and `LEADS` from `backend/tests/seed_data.py`, events G1–G5), plus:

| Key | What | Details |
|-----|------|---------|
| tom | User | role `tech_staff` (a second Technical Support member) |
| sam | User | role `safety_officer` |
| G6 | Event "Harbour Lights Festival" | `draft`, organiser dana, no coordinator, with a requirement saved directly |

Requirements recorded by alice for G1: **2 × Wireless microphone** ("Lapel, with spare batteries") and **1 × Projector** (no technical requirements). The note used is "Two lapel mics held at the AV store".

---

## AC1 — Technical Support update a requirement, saved with who and when

**TC-97-01 · An update is saved with its status, note, who and when**
- **Traces to:** AC1 · **Type:** Positive · **Depends on:** A2, A3
- **Steps:** As hana, set the microphones to Being arranged with the note, sending their `last_saved_at`.
- **Expected result:** HTTP 200 naming Being arranged. Stored: status `being_arranged`, the note, `arrangement_updated_by_id` hana, `arrangement_updated_at` between the times before and after the request. The reply's requirement shows the same, with hana's email. The type, quantity, technical requirements and `last_saved_at` are unchanged, and the projector is untouched.
- **Automated:** `test_tc_97_01_an_update_is_saved_with_who_and_when`

**TC-97-02 · Each update records who made it and when, replacing the last**
- **Traces to:** AC1 · **Type:** Positive · **Depends on:** A3, A5
- **Steps:** hana sets Being arranged; then tom sets Suitable equipment unavailable with "Only one lapel mic in stock".
- **Expected result:** Both HTTP 200. Afterwards the microphones are unavailable with tom's note, updated by tom, at a time not before hana's.
- **Automated:** `test_tc_97_02_each_update_records_who_and_when`

**TC-97-03 · The note can be changed or cleared, and every status can be set**
- **Traces to:** AC1 · **Type:** Positive · **Depends on:** A2
- **Steps:** As hana, set each status in turn; then send a blank note, then `note: null`, then a status without `note`.
- **Expected result:** Each status is stored. A blank or null note clears it; leaving `note` out keeps the stored note.
- **Automated:** `test_tc_97_03_every_status_can_be_set_and_the_note_changed`

**TC-97-04 · An update that changes nothing keeps the earlier who and when**
- **Traces to:** AC1 · **Type:** Business rule · **Depends on:** A4
- **Steps:** hana sets Being arranged with the note; tom then sends the same status and note (with extra spaces).
- **Expected result:** HTTP 200 "No changes were made to the arrangement for 2 × Wireless microphone." Still updated by hana, at the same time.
- **Automated:** `test_tc_97_04_an_update_that_changes_nothing_keeps_who_and_when`

**TC-97-05 · An update for details the coordinator has since changed is refused**
- **Traces to:** AC1, AC2 · **Type:** Negative (business rule) · **Depends on:** A5
- **Steps:** hana opens G1 (noting the microphones' `last_saved_at`). alice changes the quantity to 5. hana sends Being arranged with the note and the old `last_saved_at`.
- **Expected result:** HTTP 409 saying the update was not saved and naming the requirement as it is now (5 × Wireless microphone), with `reload: true`. Stored: quantity 5, status Requested, no note, no who or when. Sending again with the new `last_saved_at` is HTTP 200, and the requirement was read with `SELECT … FOR UPDATE` before it was saved. An update without `last_saved_at` (an older page) is HTTP 200.
- **Automated:** `test_tc_97_05_an_update_for_changed_details_is_refused`

**TC-97-06 · Only the arrangement can be changed this way**
- **Traces to:** AC1, AC2 · **Type:** Negative · **Depends on:** A2
- **Steps:** As hana, send a valid status together with `equipment_type`, `quantity` and `technical_requirements`; then send `status: "reserved"` and a note of 1,001 characters.
- **Expected result:** The first is HTTP 200 and the coordinator's details are unchanged. The others are HTTP 422 naming `status` and `note`, and nothing is stored.
- **Automated:** `test_tc_97_06_only_the_arrangement_can_be_changed`

## AC2 — Only Technical Support Staff can update; anyone else is denied and nothing changes

**TC-97-07 · Everyone else is refused without details**
- **Traces to:** AC2 · **Type:** Negative (authorisation) · **Depends on:** A7
- **Steps:** Send Being arranged for the microphones as alice (G1's coordinator), ben and chloe, dana (G1's organiser), evan, farah, gus, admin, lena and sam.
- **Expected result:** HTTP 403 "Only Technical Support Staff can update equipment arrangements." each time, with no requirement, event title or equipment type in the reply.
- **Automated:** `test_tc_97_07_everyone_else_is_refused_without_details`

**TC-97-08 · A refused update changes nothing**
- **Traces to:** AC2 · **Type:** Negative · **Depends on:** A7
- **Steps:** With the microphones Being arranged by hana with the note, make every refused request in TC-97-07, with a different status and note.
- **Expected result:** Every requirement is stored exactly as before (details, status, note, who and when, when last saved), G1 is unchanged, and no notification or email is added.
- **Automated:** `test_tc_97_08_a_refused_update_changes_nothing`

**TC-97-09 · The stored role decides, on every request**
- **Traces to:** AC2 · **Type:** Negative (authorisation) · **Depends on:** A7
- **Steps:** Mint tokens for hana and farah. Change hana's stored role to attendee and farah's to tech_staff, then update with the old tokens.
- **Expected result:** hana → HTTP 403 and nothing stored; farah → HTTP 200, recorded as updated by farah.
- **Automated:** `test_tc_97_09_the_stored_role_decides_on_every_request`

**TC-97-10 · Signed-out users, unknown events and requirements, drafts and closed events**
- **Traces to:** AC2 · **Type:** Negative · **Depends on:** A6, A7
- **Steps:** Update with no token and with a deleted user's token. As hana and as farah: an unknown event ID, and G6's requirement (draft). As hana: an unknown requirement ID, the projector's ID under G2, and a requirement of G3 (cancelled). As farah: an unknown requirement ID.
- **Expected result:** HTTP 401 twice; "Event not found." (404) for the unknown event and the draft for both users; for hana "Equipment requirement not found." (404) for the unknown and the other event's requirement, and 409 naming cancelled for G3; farah's unknown requirement is 403 (permission before the requirement). Nothing is stored.
- **Automated:** `test_tc_97_10_signed_out_unknown_drafts_and_closed`

## AC3 — A failed save leaves the requirements unchanged and shows an error

**TC-97-11 · A failed save changes nothing and says so**
- **Traces to:** AC3 · **Type:** Negative (failure) · **Depends on:** A8
- **Steps:** With the microphones Being arranged by hana, make the commit fail while tom sets them unavailable with a new note.
- **Expected result:** HTTP 503 `retryable: true`, "The arrangement was not saved, and the recorded requirements are unchanged. Please try again.", with no internal error text and no `requirement`. Every requirement is stored exactly as before, still updated by hana.
- **Automated:** `test_tc_97_11_a_failed_save_changes_nothing`

**TC-97-12 · A failed read is a failure, never "not found"**
- **Traces to:** AC3 · **Type:** Negative (failure) · **Depends on:** A8
- **Steps:** Make reads of the event, then of the requirements, fail while hana updates the microphones.
- **Expected result:** HTTP 503 `retryable: true` with the same message each time, never 404; nothing is stored.
- **Automated:** `test_tc_97_12_a_failed_read_is_a_failure`

**TC-97-13 · Trying again after a failure saves the update**
- **Traces to:** AC3 · **Type:** Negative then positive · **Depends on:** A8
- **Steps:** Make the commit fail while hana sends Being arranged, then send it again.
- **Expected result:** The first → HTTP 503 and nothing stored; the second → HTTP 200, stored with hana and the time.
- **Automated:** `test_tc_97_13_trying_again_saves_the_update`

## Frontend

`EquipmentRequirementsPage` (`/events/:eventId/equipment`). The API is mocked with replies that mirror the backend contract.

**TC-97-14 · The page shows who last updated each arrangement and when, and sends what was seen** — AC1 · `shows who updated each arrangement and when, and sends the details it showed`

**TC-97-15 · After an update, the new status, note, who and when are shown** — AC1 · `shows the update, who made it and when once it is saved`

**TC-97-16 · A refusal is shown and nothing on the page changes** — AC2 · `shows a refusal and leaves the requirements as they were`

**TC-97-17 · A failed save shows the error, keeps the requirements and what was entered, and Update tries again** — AC3 · `keeps the requirements and the entry when a save fails, and saves on trying again`

**TC-97-18 · With no reply, the page says the requirements are unchanged and to check the connection** — AC3 · `says the requirements are unchanged when there is no reply`

**TC-97-19 · When the coordinator changed the requirement, the page says so and shows the new details** — AC1, A5 · `reloads the new details when the coordinator changed the requirement`

---

## Traceability matrix

| AC | Test cases |
|----|------------|
| AC1 | 01, 02, 03, 04, 05, 06, 14, 15, 19 · also TC-42-21, 22, 35 |
| AC2 | 05, 06, 07, 08, 09, 10, 16 · also TC-42-23 |
| AC3 | 11, 12, 13, 17, 18 · also TC-42-28 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Is "updating a requirement" setting its arrangement status and a note (as built)? Should Technical Support also be able to change the type, quantity or technical requirements, or mark a requirement arranged without reserving equipment through SCRUM-44? | A2, TC-97-03, 06 |
| Q2 | Is the latest update, with who made it and when, enough (as built), or should every update be kept as a history? Should pressing Update without changing anything record a new who and when? | A3, A4, TC-97-02, 04 |
| Q3 | When the coordinator changes a requirement while Technical Support are updating it, should the update be refused so they check the new details (as built)? | A5, TC-97-05, 19 |
| Q4 | Is "not saved, the recorded requirements are unchanged, please try again" enough explanation of a failed save? | A8, TC-97-11, 17, 18 |
