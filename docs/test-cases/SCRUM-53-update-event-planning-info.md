# SCRUM-53 — Update Event Planning Information (Normal Fields): Test Cases

**User story:** As an Event Coordinator, I want to edit the fields I'm permitted to update under the agreed editing rules so that non-critical event information stays current as arrangements develop.

**Created:** 28 Sep 2026 · **Automated tests:** `backend/tests/test_update_event_planning_info.py` · **Endpoint:** `PATCH /api/events/<id>` · **Related:** SCRUM-34 (view), SCRUM-52 (restricted fields), SCRUM-46 (change review)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | The coordinator can edit fields classified as normal updates for their role, per the agreed editing rules. |
| AC2 | Successful saving updates the selected event, and the changes remain visible when it is reopened. |
| AC3 | Invalid entries prevent saving, identify the necessary corrections, and leave previously saved information unchanged. |
| AC4 | If saving fails for reasons other than validation, the coordinator is informed, previously saved information remains unchanged, and entered edits remain available for retry. |
| AC5 | Fields classified as important changes are not editable through this normal-edit flow (see SCRUM-52). |

## Agreed editing rules (working assumptions)

Each rule is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **R1 — Normal fields:** `title`, `purpose`, `description` and `accessibility_needs`. These are the only fields this flow saves. *(Q1, Q5)*
- **R2 — Important fields:** `venue_id`, `start_time`, `end_time`, `expected_attendance`, `venue_requirements` and `registration_required`, because changing them affects venue bookings, venue capacity or attendees. They are never saved by this flow; SCRUM-52 defines how the coordinator is told to use the review process instead. *(Q2)*
- **R3 — Other fields:** `status`, `organiser_id`, `coordinator_id`, `coordinator_assigned_at`, `created_at`, `id`, the SCRUM-29/32 request tracking fields (`submitted_at`, `last_saved_at`, `decision_note`, `decided_at`, `decided_by_id`) and `equipment_requirements` (recorded through SCRUM-42) are managed by other stories and cannot be changed here.
- **R4 — Who can edit:** the same rule as viewing (SCRUM-34, A1). Only the event's current coordinator, while their role is still `coordinator`, checked against the database on every request.
- **R5 — Cancelled events** cannot be edited (HTTP 409). *(Q3)*
- **R6 — Title:** required text, 1–255 characters after surrounding spaces are removed (255 is the database column limit).
- **R7 — Purpose, description and accessibility needs:** optional text, up to 5,000 characters each after surrounding spaces are removed. Sending `null`, an empty string or only spaces clears the field, and the view then shows it as *not recorded*. *(Q4)*
- **R8 — All or nothing:** if any field in a save is invalid, nothing in that save is stored, and every invalid field is identified at once.
- **R9 — Retry:** a failed save changes nothing, and sending the same edits again succeeds once the problem clears. The backend returns `retryable: true`; keeping the entered values on screen is the frontend's job.

## Responses

| Situation | HTTP | Body |
|-----------|------|------|
| Saved | 200 | `message` plus the event's planning information, exactly as `GET /api/events/<id>/planning` returns it |
| Body is not a JSON object | 400 | `error` |
| Invalid or non-editable fields, or no fields | 422 | `error`, and `fields` mapping each field name to what needs correcting |
| Not logged in, expired token, deleted user | 401 | `error` |
| Not the event's current coordinator | 403 | `error`, with no event details |
| Event does not exist | 404 | `error` |
| Event is cancelled | 409 | `error` |
| Database failure while loading or saving | 503 | `error`, `retryable: true` |

Checks run in this order: 401, 404, 403, 409, 400/422, then the save. So a user who may not edit the event is refused before their input is examined.

## Seed data (EU-SEED)

Reset the database to this data before **every** test case. Users and the Charity Gala, Product Launch and Tech Summit come from `backend/tests/seed_data.py`. The other events are created in the test file.

| Ref | Title | Status | Coordinator | Venue | Description | Start – End |
|-----|-------|--------|-------------|-------|-------------|-------------|
| E1 | Harbour Lights Festival | submitted | alice | Aurora Ballroom | "Waterfront lantern festival with live music and food stalls." | Sat 12 Dec 2026 17:00 – 22:00 |
| E2 | Charity Gala | submitted | alice | *not recorded* | *not recorded* | Sat 5 Dec 2026 18:00 – 23:00 |
| E3 | Product Launch | submitted | ben | *not recorded* | *not recorded* | Fri 20 Nov 2026 14:00 – 16:00 |
| E4 | Tech Summit 2026 | submitted | *none* | *not recorded* | *not recorded* | Tue 10 Nov 2026 09:00 – 17:00 |
| E5 | Winter Networking Night | cancelled | alice | *not recorded* | *not recorded* | Thu 1 Oct 2026 09:00 – 11:00 |

Users are as in SCRUM-34: alice, ben and chloe (coordinators), admin, dana and evan (organisers), farah (attendee), gus (venue staff), hana (tech staff).

---

## AC1 — The coordinator can edit normal fields

**TC-53-01 · Update the description**
- **Traces to:** AC1, AC2 · **Type:** Happy path
- **Preconditions:** EU-SEED loaded; logged in as `alice`.
- **Steps:** Change E1's description to "Now with a drone light show." and save.
- **Expected result:** Saved (HTTP 200) with a confirmation message. The response shows the new description.
- **Automated:** `test_coordinator_can_update_the_description`

**TC-53-02 · Update the title**
- **Traces to:** AC1 · **Type:** Happy path · **Depends on:** Q1
- **Preconditions:** As TC-53-01.
- **Steps:** Change E1's title to "Harbour Lights Festival 2026" and save.
- **Expected result:** Saved. The response shows the new title.
- **Automated:** `test_coordinator_can_update_the_title`

**TC-53-03 · Update both normal fields at once**
- **Traces to:** AC1 · **Type:** Happy path
- **Preconditions:** As TC-53-01.
- **Steps:** Change E1's title and description in one save.
- **Expected result:** Both are saved.
- **Automated:** `test_title_and_description_can_be_updated_together`

**TC-53-04 · Only the submitted fields change**
- **Traces to:** AC1, AC2 · **Type:** Negative (side effect)
- **Preconditions:** As TC-53-01.
- **Steps:** 1. Note every stored field of E1. 2. Change only the description and save. 3. Compare.
- **Expected result:** Only the description differs.
- **Automated:** `test_only_the_submitted_fields_change`

**TC-53-05 · Fill in a description that was never recorded**
- **Traces to:** AC1 · **Type:** Happy path
- **Preconditions:** EU-SEED loaded; logged in as `alice`.
- **Steps:** Give Charity Gala (E2) a description and save.
- **Expected result:** Saved. The description is no longer listed as *not recorded*.
- **Automated:** `test_a_description_that_was_not_recorded_can_be_added`

**TC-53-32 · Update the purpose and accessibility needs**
- **Traces to:** AC1, AC2 · **Type:** Happy path · **Depends on:** Q5
- **Preconditions:** As TC-53-01.
- **Steps:** Change E1's purpose to "Mark the harbour's 50th anniversary." and its accessibility needs to "Wheelchair seating near the stage.", then save.
- **Expected result:** Both are saved and shown in the response.
- **Automated:** `test_coordinator_can_update_purpose_and_accessibility_needs`

**TC-53-06 · Clear the description**
- **Traces to:** AC1 · **Type:** Boundary · **Depends on:** Q4
- **Preconditions:** As TC-53-01.
- **Steps:** Save E1 with description `null`; repeat with `""` and with `"   "`.
- **Expected result:** Each time the description is stored as empty and shown as *not recorded*.
- **Automated:** `test_description_can_be_cleared`

**TC-53-07 · Surrounding spaces are removed**
- **Traces to:** AC1 · **Type:** Boundary
- **Preconditions:** As TC-53-01.
- **Steps:** Save E1 with title `"  Harbour Lights  "` and description `"  Lanterns.  "`.
- **Expected result:** Stored as "Harbour Lights" and "Lanterns.".
- **Automated:** `test_surrounding_spaces_are_removed`

**TC-53-08 · Saving an unchanged value is allowed**
- **Traces to:** AC1 · **Type:** Boundary
- **Preconditions:** As TC-53-01.
- **Steps:** Save E1 with its current title.
- **Expected result:** Saved (HTTP 200), nothing changes.
- **Automated:** `test_saving_an_unchanged_value_is_allowed`

## AC2 — Saved changes update the event and remain visible when reopened

**TC-53-09 · Response shows the saved event**
- **Traces to:** AC2 · **Type:** Happy path
- **Preconditions:** As TC-53-01.
- **Steps:** Change E1's description and save.
- **Expected result:** Apart from `message`, the response is identical to what `GET /api/events/<id>/planning` returns for E1 afterwards.
- **Automated:** `test_response_shows_the_event_as_saved`

**TC-53-10 · Changes remain visible when the event is reopened**
- **Traces to:** AC2 · **Type:** Happy path
- **Preconditions:** As TC-53-01.
- **Steps:** 1. Change E1's title and description and save. 2. Reopen E1's planning information (SCRUM-34).
- **Expected result:** The new title and description are shown.
- **Automated:** `test_changes_remain_visible_when_the_event_is_reopened`

**TC-53-11 · Only the selected event changes**
- **Traces to:** AC2 · **Type:** Negative (side effect)
- **Preconditions:** As TC-53-01.
- **Steps:** 1. Note every stored field of E2. 2. Change E1's description and save. 3. Compare E2.
- **Expected result:** E2 is unchanged.
- **Automated:** `test_other_events_are_not_changed`

## AC3 — Invalid entries prevent saving and identify corrections

For every case in this section: the response is HTTP 422 with a `fields` entry naming each field to correct, and every stored field of the event is unchanged.

**TC-53-12 · Blank title**
- **Traces to:** AC3 · **Type:** Negative
- **Test data:** title = `""`, `"   "`, `null`.
- **Expected result:** `fields.title` asks for a title.
- **Automated:** `test_blank_title_is_rejected`

**TC-53-13 · Title length boundary**
- **Traces to:** AC3 · **Type:** Boundary
- **Test data:** 255 characters (accepted), 256 characters (rejected).
- **Expected result:** 255 saves; 256 is rejected with `fields.title`.
- **Automated:** `test_title_length_limit`

**TC-53-14 · Optional text length boundary**
- **Traces to:** AC3 · **Type:** Boundary · **Depends on:** Q4
- **Test data:** for each of purpose, description and accessibility needs: 5,000 characters (accepted), 5,001 characters (rejected).
- **Expected result:** 5,000 saves; 5,001 is rejected with a `fields` entry for that field.
- **Automated:** `test_description_length_limit`

**TC-53-15 · Values that are not text**
- **Traces to:** AC3 · **Type:** Negative
- **Test data:** title = `123`, `true`, `["a"]`; description = `42`, `{"a": 1}`; purpose = `7`; accessibility needs = `false`.
- **Expected result:** Rejected with a `fields` entry for the field.
- **Automated:** `test_values_that_are_not_text_are_rejected`

**TC-53-16 · One invalid field stops the whole save**
- **Traces to:** AC3 · **Type:** Negative · **Depends on:** R8
- **Test data:** valid description, blank title.
- **Expected result:** Rejected. The valid description is **not** saved either.
- **Automated:** `test_one_invalid_field_prevents_saving_the_others`

**TC-53-17 · Every invalid field is identified at once**
- **Traces to:** AC3 · **Type:** Negative
- **Test data:** blank title and a 5,001-character description.
- **Expected result:** `fields` names both title and description.
- **Automated:** `test_every_invalid_field_is_identified`

**TC-53-18 · Nothing to save**
- **Traces to:** AC3 · **Type:** Negative
- **Test data:** `{}`.
- **Expected result:** HTTP 422 saying there are no changes to save.
- **Automated:** `test_empty_save_is_rejected`

**TC-53-19 · Malformed request**
- **Traces to:** AC3 · **Type:** Negative
- **Test data:** a JSON list, a JSON string, a body that is not JSON.
- **Expected result:** HTTP 400. The event is unchanged.
- **Automated:** `test_body_that_is_not_a_json_object_is_rejected`

**TC-53-20 · Unknown and system fields**
- **Traces to:** AC3 · **Type:** Negative · **Depends on:** R3
- **Test data:** each of `colour`, `status`, `organiser_id`, `coordinator_id`, `coordinator_assigned_at`, `created_at`, `id`, `equipment_requirements`, `decision_note`, `submitted_at`.
- **Expected result:** Rejected with a `fields` entry saying the field can't be changed here.
- **Automated:** `test_unknown_and_system_fields_are_rejected`

## AC4 — Save failures are reported and can be retried

**TC-53-21 · Save fails**
- **Traces to:** AC4 · **Type:** Negative (failure)
- **Preconditions:** EU-SEED loaded; logged in as `alice`; writes to the database fail (in automated tests, every `UPDATE` raises an `OperationalError`).
- **Steps:** Change E1's description and save.
- **Expected result:** HTTP 503, `retryable: true`, with a message saying the changes were not saved. No event details are returned. E1 is unchanged.
- **Automated:** `test_save_failure_informs_the_coordinator_and_offers_retry`, `test_save_failure_leaves_the_event_unchanged`

**TC-53-22 · Database unavailable before saving**
- **Traces to:** AC4 · **Type:** Negative (failure)
- **Preconditions:** As TC-53-21, but every query fails.
- **Expected result:** HTTP 503 with `retryable: true`, not 401, 403 or 404.
- **Automated:** `test_load_failure_is_reported_as_retryable`

**TC-53-23 · Retrying the same edits succeeds**
- **Traces to:** AC4 · **Type:** Happy path (recovery)
- **Preconditions:** TC-53-21 has just failed; the database is then restored.
- **Steps:** Send exactly the same edits again.
- **Expected result:** Saved, and the new description is shown.
- **Automated:** `test_retrying_the_same_edits_succeeds_once_the_database_recovers`

**TC-53-24 · Entered edits stay on screen**
- **Traces to:** AC4 · **Type:** Negative (failure, UI) · **Manual** (no frontend page yet)
- **Preconditions:** `alice` is editing E1 in the web app; the backend is then stopped.
- **Steps:** 1. Edit the description and click Save. 2. Restart the backend. 3. Click Save again.
- **Expected result:** (1) An error is shown and the typed description is still in the box. (3) It saves without retyping.

## AC5 — Important fields are not editable here

**TC-53-25 · Important fields are never saved by this flow**
- **Traces to:** AC5 · **Type:** Negative · **Depends on:** Q2
- **Preconditions:** EU-SEED loaded; logged in as `alice`.
- **Steps:** For each of `venue_id` (to another venue), `start_time` and `end_time` (to new times), `expected_attendance` (500), `venue_requirements` and `registration_required` (No), try to save E1.
- **Expected result:** The stored value is unchanged. (The response the coordinator sees is defined by SCRUM-52.)
- **Automated:** `test_important_fields_are_not_saved`

## Authorisation (cross-cutting, rule R4)

**TC-53-26 · Session required**
- **Test data:** no token, expired token, token for a deleted user.
- **Expected result:** HTTP 401. E1 is unchanged.
- **Automated:** `test_editing_requires_authentication`, `test_expired_token_is_rejected`, `test_token_for_a_deleted_user_is_rejected`

**TC-53-27 · Unknown event**
- **Expected result:** "Event not found." (HTTP 404).
- **Automated:** `test_unknown_event_returns_not_found`

**TC-53-28 · Other coordinators, unassigned events and non-coordinators are refused**
- **Test data:** `ben` and `chloe` editing E1; `alice` editing E4 (no coordinator); `admin`, `dana` (E1's organiser), `evan`, `farah`, `gus`, `hana` editing E1.
- **Expected result:** HTTP 403 with no event details. The event is unchanged.
- **Automated:** `test_coordinator_of_another_event_is_refused`, `test_no_one_can_edit_an_unassigned_event`, `test_users_who_are_not_coordinators_are_refused`

**TC-53-29 · Role change or reassignment removes access at once**
- **Steps:** 1. Reassign E1 to ben, then alice saves with her existing token. 2. Separately, change alice's role to organiser, then alice saves.
- **Expected result:** Refused (403) each time.
- **Automated:** `test_reassigned_coordinator_can_no_longer_edit`, `test_coordinator_who_changes_role_can_no_longer_edit`

**TC-53-30 · Refusal happens before input is checked**
- **Test data:** `ben` sends a blank title for E1.
- **Expected result:** HTTP 403, not 422, so nothing about the editing rules is revealed.
- **Automated:** `test_refusal_comes_before_validation`

**TC-53-31 · Cancelled event cannot be edited**
- **Traces to:** R5 · **Type:** Negative · **Depends on:** Q3
- **Steps:** `alice` changes the description of Winter Networking Night (E5).
- **Expected result:** HTTP 409 saying the event is cancelled. E5 is unchanged.
- **Automated:** `test_cancelled_event_cannot_be_edited`

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01–08, 32 |
| AC2 | 01, 04, 09, 10, 11, 32 |
| AC3 | 12–20 |
| AC4 | 21–24 |
| AC5 | 25 |
| Authorisation (R4, R5) | 26–31 |

| Type | Test cases |
|------|-----------|
| Happy path | 01, 02, 03, 05, 09, 10, 23, 32 |
| Negative | 04, 11, 12, 15–22, 24–31 |
| Boundary | 06, 07, 08, 13, 14 |
| Manual only | 24 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Is the event **title** a normal field the coordinator can change directly, or is renaming an event an important change that needs review (e.g. because attendees know it by name)? | R1, TC-53-02, 03, 07, 12, 13 |
| Q2 | Is the important list right? Expected attendance, venue requirements and registration required were added because they affect venue capacity, bookings and attendees. | R2, TC-53-25, SCRUM-52 |
| Q3 | Can a coordinator still edit an event that is cancelled, rejected or completed? | R5, TC-53-31 |
| Q4 | Is 5,000 characters enough? Purpose and description are required when an organiser submits a request (SCRUM-29), so should a coordinator be allowed to clear them afterwards? | R7, TC-53-06, 14 |
| Q5 | Are purpose and accessibility needs normal fields a coordinator can change directly? | R1, TC-53-32 |
