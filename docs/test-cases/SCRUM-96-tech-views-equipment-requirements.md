# SCRUM-96 — Technical Support Views an Event's Equipment Requirements: Test Cases

**User story:** As a Technical Support Staff member, I want to view an event's equipment requirements, so that I can record what is arranged as it is arranged.

**Created:** 29 Oct 2026 · **Status of all cases:** not yet run · **Automated tests:** `backend/tests/test_tech_views_equipment.py`, `frontend/src/pages/EquipmentRequirementsPage.test.jsx` (the "SCRUM-96" blocks) · **Endpoint:** `GET /api/events/<id>/equipment-requirements` (built by SCRUM-42) · **Related:** SCRUM-42 (records the requirements and already lets Technical Support view and update them: AC4, TC-42-19 to 23), SCRUM-43 and SCRUM-44 (check and reserve equipment from the same page), SCRUM-59 and SCRUM-74 (a draft is the organiser's own)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | I can open an event's equipment requirements and see the types, quantities and technical requirements. |
| AC2 | Only Technical Support Staff can view them. Anyone else is denied and nothing changes. |
| AC3 | If the requirements cannot be loaded, a message explains why and offers a retry. |

## Working assumptions (to confirm)

- **A1 — Built on SCRUM-42:** the endpoint, the page (`/events/:eventId/equipment`) and the Technical Support list that links to it (`/equipment-requests`) already exist from SCRUM-42 AC4. This story checks them from Technical Support's side and adds the one rule that was missing (A3). No new table, field or page.
- **A2 — "Only Technical Support Staff":** Technical Support Staff and also **the event's current coordinator**, who records the requirements (SCRUM-42 A9). Refusing the coordinator would stop them seeing or editing what they record, so SCRUM-42 is left unchanged. Everyone else is refused, including the organiser, other coordinators, the Coordinator Lead, admins, Venue Staff, Safety Officers and attendees. *(Q1)*
- **A3 — Which events:** every event that has left draft, including cancelled and rejected ones, which are read-only (SCRUM-42 A4). A **draft** is still the organiser's own (SCRUM-59, SCRUM-74 A2): its equipment requirements are "Event not found." (HTTP 404) for everyone, the same reply as an unknown ID, so neither its title nor the organiser's note is shown. A draft never has a coordinator, so it can't have recorded requirements. *(Q2)*
- **A4 — What Technical Support see:** the event (title, status, times, coordinator), the organiser's note from the request (SCRUM-42 A2), and each requirement's equipment type, quantity and technical requirements ("None recorded" when blank), in the order recorded, with its arrangement status, note and who last updated it, so they can see what has been arranged so far. *(Q3)*
- **A5 — Denied, and nothing changes:** a refusal is HTTP 403 "You are not allowed to view this event's equipment requirements." with no event or requirement details. Viewing, allowed or refused, never changes a requirement, its arrangement or the event, and sends no notification or email. The role is read from the database on every request, so a Technical Support member moved to another role is refused at once, even with their old token.
- **A6 — A failed load:** HTTP 503 `retryable: true`, "The equipment requirements could not be loaded. Please try again.", never an empty list or "not found". The page shows that message (or, with no reply at all, "…could not be loaded. Check your connection and try again.") with a **Retry** button. Retry loads again without leaving the page. Refusals (401, 403, 404) are shown without Retry, because trying again would not help. The message can't name the database problem, which would be internal detail; it says the load failed and what to do. *(Q4)*

## Seed data (TS-SEED)

EQ-SEED from SCRUM-42 (users `USERS` and `LEADS` from `backend/tests/seed_data.py`, events G1–G5), plus:

| Key | What | Details |
|-----|------|---------|
| sam | User | role `safety_officer` |
| G6 | Event "Harbour Lights Festival" | `draft`, organiser dana, no coordinator, 2026-12-12 19:00 – 22:00, organiser's note "Smoke machine and strobe lights" |

Requirements recorded by alice for G1: **2 × Wireless microphone** ("Lapel, with spare batteries") and **1 × Projector** (no technical requirements).

---

## AC1 — Technical Support open an event's requirements and see them

**TC-96-01 · Technical Support see each requirement's type, quantity and technical requirements**
- **Traces to:** AC1 · **Type:** Positive · **Depends on:** A4
- **Steps:** As hana (not related to G1 in any way), open G1's equipment requirements.
- **Expected result:** HTTP 200 with G1 (title, status, times, coordinator alice) and the organiser's note, then 2 × Wireless microphone "Lapel, with spare batteries" and 1 × Projector with technical requirements null, in that order, each Requested. `can_update_arrangements` true, `can_edit` false, `message` null.
- **Automated:** `test_tc_96_01_technical_support_see_types_quantities_and_technical_requirements`

**TC-96-02 · Every event that has left draft can be opened**
- **Traces to:** AC1 · **Type:** Positive · **Depends on:** A3
- **Steps:** Record a requirement for G1 (approved), G2 (submitted) and G5 (under review), and directly against G3 (cancelled) and G4 (rejected). As hana, open each.
- **Expected result:** HTTP 200 each time with that event's requirement. G3 and G4 are read-only (`can_update_arrangements` false) with a notice naming their status.
- **Automated:** `test_tc_96_02_every_event_that_has_left_draft_can_be_opened`

**TC-96-03 · Each event on the equipment requests list opens with its requirements**
- **Traces to:** AC1 · **Type:** Positive · **Depends on:** A1
- **Steps:** Record requirements for G1 (two) and G2 (one). As hana, load the equipment requests list, then open each of these events from it.
- **Expected result:** Each listed event opens (HTTP 200) with as many requirements as the list said.
- **Automated:** `test_tc_96_03_each_listed_event_opens_with_its_requirements`

**TC-96-04 · Technical Support see what has been arranged so far**
- **Traces to:** AC1 · **Type:** Positive · **Depends on:** A4
- **Steps:** As hana, mark the microphones Being arranged with the note "Two lapel mics held at the AV store", then open G1 again.
- **Expected result:** The microphones show "Being arranged", the note, and that hana updated them; type, quantity and technical requirements are unchanged.
- **Automated:** `test_tc_96_04_technical_support_see_what_has_been_arranged`

**TC-96-05 · A draft's equipment requirements are not found**
- **Traces to:** AC1, AC2 · **Type:** Negative · **Depends on:** A3
- **Steps:** Open G6 (draft) as hana and as dana (its organiser).
- **Expected result:** HTTP 404 "Event not found.", the same as an unknown ID, with no title, times or organiser's note in the reply.
- **Automated:** `test_tc_96_05_a_drafts_equipment_requirements_are_not_found`

## AC2 — Only Technical Support Staff can view them; anyone else is denied and nothing changes

**TC-96-06 · Everyone else is refused without the event's details**
- **Traces to:** AC2 · **Type:** Negative (authorisation) · **Depends on:** A2, A5
- **Steps:** Open G1's requirements as ben and chloe (other coordinators), dana (its organiser), evan, farah (attendee), gus (Venue Staff), admin, lena (Coordinator Lead) and sam (Safety Officer).
- **Expected result:** HTTP 403 "You are not allowed to view this event's equipment requirements." each time. The reply contains no requirements, no event title and no equipment type.
- **Automated:** `test_tc_96_06_everyone_else_is_refused_without_details`

**TC-96-07 · A refused view changes nothing**
- **Traces to:** AC2 · **Type:** Negative · **Depends on:** A5
- **Steps:** With G1's requirements recorded, and one marked Being arranged with a note, make every refused request in TC-96-06, then hana's allowed view.
- **Expected result:** Every requirement is stored exactly as before (type, quantity, technical requirements, status, note, who updated it and when, when last saved), G1 is unchanged, no notification is added and no email is queued.
- **Automated:** `test_tc_96_07_a_refused_view_changes_nothing`

**TC-96-08 · Who may view is decided by the stored role, on every request**
- **Traces to:** AC2 · **Type:** Negative (authorisation) · **Depends on:** A2, A5
- **Steps:** Mint tokens for hana and farah. Change hana's stored role to attendee and farah's to tech_staff, then open G1's requirements with the old tokens. Then reassign G1 from alice to ben and open it as alice.
- **Expected result:** hana → HTTP 403; farah → HTTP 200; alice, no longer its coordinator → HTTP 403.
- **Automated:** `test_tc_96_08_the_stored_role_decides_on_every_request`

**TC-96-09 · Signed-out users and unknown events**
- **Traces to:** AC2 · **Type:** Negative
- **Steps:** Open G1's requirements with no token, and with the token of a user who has been deleted. Open an unknown event ID as hana and as farah.
- **Expected result:** HTTP 401 both times (the deleted user's reply says "Your session is no longer valid. Please log in again."). HTTP 404 "Event not found." for both unknown-ID requests: the 404 comes before the 403, as for every endpoint.
- **Automated:** `test_tc_96_09_signed_out_users_and_unknown_events`

## AC3 — A failed load explains why and offers a retry

**TC-96-10 · A failed read of the requirements is a failure, not an empty list**
- **Traces to:** AC3 · **Type:** Negative (failure) · **Depends on:** A6
- **Steps:** Make reads of the requirements fail while hana opens G1.
- **Expected result:** HTTP 503, `retryable: true`, "The equipment requirements could not be loaded. Please try again.", with no `requirements`, `event` or `message` in the reply, and no internal error text.
- **Automated:** `test_tc_96_10_a_failed_read_of_the_requirements_is_a_failure`

**TC-96-11 · A failed read of the event is a failure, not "not found"**
- **Traces to:** AC3 · **Type:** Negative (failure) · **Depends on:** A6
- **Steps:** Make reads of the event fail while hana opens G1.
- **Expected result:** HTTP 503, `retryable: true`, the same message; never 404.
- **Automated:** `test_tc_96_11_a_failed_read_of_the_event_is_a_failure`

**TC-96-12 · Trying again after a failure loads the requirements, and the failure changed nothing**
- **Traces to:** AC3 · **Type:** Negative then positive · **Depends on:** A6
- **Steps:** Make the first load fail, then open G1 again as hana.
- **Expected result:** The first load → HTTP 503; the second → HTTP 200 with both requirements as recorded.
- **Automated:** `test_tc_96_12_trying_again_loads_the_requirements`

## Frontend

`EquipmentRequirementsPage` (`/events/:eventId/equipment`). The API is mocked with replies that mirror the backend contract.

**TC-96-13 · Technical Support see each requirement's type, quantity and technical requirements, with no record or edit form** — AC1 · `shows Technical Support each requirement's type, quantity and technical requirements`

**TC-96-14 · A refusal or a missing event is shown without Retry or any requirements** — AC2 · `shows a refusal or a missing event without Retry`

**TC-96-15 · A failed load shows why and Retry loads the requirements** — AC3 · `explains a failed load and loads the requirements on Retry`

**TC-96-16 · With no reply at all, the page says to check the connection and Retry stays until a load works** — AC3 · `asks to check the connection when there is no reply, and keeps Retry until a load works`

---

## Traceability matrix

| AC | Test cases |
|----|------------|
| AC1 | 01, 02, 03, 04, 05, 13 · also TC-42-19, 20, 35, 38 |
| AC2 | 05, 06, 07, 08, 09, 14 · also TC-42-23, 37 |
| AC3 | 10, 11, 12, 15, 16 · also TC-42-29, 37 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | AC2 says only Technical Support Staff can view the requirements. Should the event's coordinator, who records them (SCRUM-42), keep seeing them (as built)? Should the organiser or the Coordinator Lead see them too? | A2, TC-96-06, 08 |
| Q2 | Should Technical Support see the requirements of submitted and under-review events (as built, so they can prepare early), or only once an event is approved? Drafts are hidden (as built). | A3, TC-96-02, 05 |
| Q3 | Should Technical Support see the organiser's free-text equipment note alongside the recorded requirements (as built)? | A4, TC-96-01 |
| Q4 | Is "could not be loaded, please try again" enough explanation of a failed load, or should the message say more, for example to contact support if it keeps failing? | A6, TC-96-10, 15, 16 |
