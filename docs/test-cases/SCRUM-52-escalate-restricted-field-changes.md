# SCRUM-52 — Escalate Restricted-Field Changes for Review: Test Cases

**User story:** As an Event Coordinator, I want to be stopped from silently saving changes to fields that affect existing arrangements so that important changes go through the agreed review process instead of taking effect unreviewed.

**Created:** 29 Sep 2026 · **Automated tests:** `backend/tests/test_escalate_restricted_field_changes.py` · **Endpoint:** `PATCH /api/events/<id>` (the SCRUM-53 normal-edit flow) · **Related:** SCRUM-53 (normal edits), SCRUM-46 (the review process), SCRUM-34 (view)

## Acceptance criteria

| ID | Criterion |
|----|-----------|
| AC1 | Attempting to change a field classified as an important change does not save it through the normal-edit flow. |
| AC2 | The coordinator is informed that the change requires the review process, with a clear next step (e.g. how to initiate that process). |
| AC3 | The event's previously saved information for that field remains unchanged until the review process concludes. |
| AC4 | The coordinator's other, non-restricted edits in the same session are unaffected by the block on the restricted field. |

## Working assumptions

Each one is tied to an open question below. If the customer answers differently, update the affected test cases before implementation.

- **B1 — Restricted fields:** `venue_id`, `start_time` and `end_time`, because they affect venue bookings and attendees. This is the "important" list from SCRUM-53, rule R2. *(Q1)*
- **B2 — What counts as a change:** a restricted field sent with its current value is not a change and is ignored, because edit forms often send every field back. Times are compared as dates and times, so `2026-12-12T17:00` equals `2026-12-12T17:00:00`. Sending `null` for a recorded venue or time is a change.
- **B3 — Format check only:** a restricted value must be well-formed (venue: a whole number or `null`; times: an ISO 8601 date and time) or the save is rejected with a correction, as in SCRUM-53. Whether the change itself makes sense (the venue exists and is free, end after start) is left to the review process. *(Q2)*
- **B4 — Only restricted changes:** nothing is saved, and the response is HTTP 409 with `requires_review`.
- **B5 — Mixed with normal edits:** the valid normal edits are saved (HTTP 200), and the response also carries `requires_review` for the blocked fields. *(Q3)*
- **B6 — Invalid input still stops everything:** if any normal field is invalid, or a field can't be changed at all (SCRUM-53, rules R3 and R8), nothing is saved (HTTP 422). `requires_review` is still included, so the coordinator learns everything in one attempt.
- **B7 — Next step:** `requires_review.next_step` tells the coordinator to submit a change request, via `POST /api/events/<id>/change-requests` (SCRUM-46, not yet built). `requires_review.requested` repeats the values the coordinator entered so they don't have to retype them. *(Q4)*
- **B8 — No automatic request:** blocking a change does not create a change request by itself. The coordinator chooses to submit one. *(Q4)*
- **B9 — Order of checks:** as in SCRUM-53. Refusals (401, 404, 403, cancelled 409) come first and never mention review.

## Response when a restricted change is blocked

```json
"requires_review": {
  "fields": ["venue_id", "start_time"],
  "requested": {"venue_id": 7, "start_time": "2026-12-12T18:00:00"},
  "message": "The venue and start time affect existing arrangements, so they can't be changed directly. Submit a change request to have them reviewed.",
  "next_step": {
    "action": "Submit a change request",
    "method": "POST",
    "url": "/api/events/42/change-requests"
  }
}
```

`fields` is always in the order venue, start time, end time.

| Situation | HTTP | Saved | Body |
|-----------|------|-------|------|
| Only restricted fields changed | 409 | nothing | `error`, `requires_review` |
| Restricted plus valid normal fields | 200 | the normal fields | `message`, the event's planning information, `requires_review` |
| Restricted plus an invalid or non-editable field | 422 | nothing | `error`, `fields`, `requires_review` |
| Restricted fields sent unchanged | as SCRUM-53 | as SCRUM-53 | no `requires_review` |

## Seed data (ER-SEED)

The same as SCRUM-53 (EU-SEED). The main event is E1, Harbour Lights Festival: coordinator `alice`, venue Aurora Ballroom, 12 Dec 2026 17:00 – 22:00. A second venue, Bayfront Pavilion, exists to move to.

---

## AC1 — Restricted changes are not saved

**TC-52-01 · Change the venue**
- **Traces to:** AC1, AC2 · **Type:** Negative
- **Preconditions:** ER-SEED loaded; logged in as `alice`.
- **Steps:** Change E1's venue to Bayfront Pavilion and save.
- **Expected result:** HTTP 409 with `requires_review` naming `venue_id`. E1 is still at Aurora Ballroom.
- **Automated:** `test_each_restricted_field_is_blocked` (venue)

**TC-52-02 · Change the start or end time**
- **Traces to:** AC1 · **Type:** Negative
- **Steps:** Separately, change E1's start time to 18:00 and its end time to 23:00.
- **Expected result:** As TC-52-01, naming `start_time` or `end_time`. Times are unchanged.
- **Automated:** `test_each_restricted_field_is_blocked` (start time, end time)

**TC-52-03 · Change all three at once**
- **Traces to:** AC1 · **Type:** Negative
- **Expected result:** HTTP 409. `requires_review.fields` is `["venue_id", "start_time", "end_time"]`. Nothing changes.
- **Automated:** `test_several_restricted_fields_are_blocked_together`

**TC-52-04 · Remove the venue or a time**
- **Traces to:** AC1 · **Type:** Boundary · **Depends on:** B2
- **Test data:** `venue_id: null`, `start_time: null`.
- **Expected result:** Treated as a change: HTTP 409, nothing changes.
- **Automated:** `test_removing_a_restricted_value_is_a_change`

**TC-52-05 · Restricted fields sent with their current values**
- **Traces to:** AC1, AC4 · **Type:** Boundary · **Depends on:** B2
- **Steps:** Save E1 with its current venue, start and end time (in both `…T17:00` and `…T17:00:00` form), plus a new description.
- **Expected result:** HTTP 200. The description is saved. There is no `requires_review`.
- **Automated:** `test_restricted_fields_sent_unchanged_are_not_blocked`

**TC-52-06 · Badly formed restricted values**
- **Traces to:** AC1 · **Type:** Negative · **Depends on:** B3
- **Test data:** `venue_id: "abc"`, `venue_id: true`, `start_time: "next Friday"`, `end_time: 1700`.
- **Expected result:** HTTP 422 with a `fields` entry for the field. Nothing changes.
- **Automated:** `test_badly_formed_restricted_values_need_correction`

## AC2 — The coordinator is told review is needed and what to do next

**TC-52-07 · Message explains the review and names the fields**
- **Traces to:** AC2 · **Type:** Happy path
- **Steps:** Change E1's venue and start time.
- **Expected result:** `requires_review.message` mentions review and a change request, and names "venue" and "start time" in words (not `venue_id`).
- **Automated:** `test_message_explains_that_review_is_needed`

**TC-52-08 · Next step points to this event's change request**
- **Traces to:** AC2 · **Type:** Happy path · **Depends on:** Q4
- **Expected result:** `next_step` is "Submit a change request", `POST /api/events/<E1 id>/change-requests`.
- **Automated:** `test_next_step_is_submitting_a_change_request_for_this_event`

**TC-52-09 · Requested values are kept for the change request**
- **Traces to:** AC2 · **Type:** Happy path
- **Expected result:** `requires_review.requested` holds exactly the venue and start time the coordinator entered.
- **Automated:** `test_requested_values_are_returned_for_the_change_request`

**TC-52-10 · Refused users are not told about review**
- **Traces to:** AC2 · **Type:** Negative (authorisation) · **Depends on:** B9
- **Steps:** `ben` (another event's coordinator) tries to change E1's venue. Separately, `alice` tries to change the venue of Winter Networking Night (cancelled).
- **Expected result:** HTTP 403 and HTTP 409 (cancelled) respectively, with no `requires_review`.
- **Automated:** `test_refused_requests_do_not_mention_review`

## AC3 — Saved information stays unchanged

**TC-52-11 · Repeated attempts change nothing**
- **Traces to:** AC3 · **Type:** Negative
- **Steps:** Try to change E1's venue three times.
- **Expected result:** Every stored field of E1 is unchanged.
- **Automated:** `test_repeated_attempts_change_nothing`

**TC-52-12 · A blocked change does not slip in with a later save**
- **Traces to:** AC3 · **Type:** Negative
- **Steps:** 1. Try to change E1's venue (blocked). 2. Save a new description on its own.
- **Expected result:** The description is saved. The venue is still Aurora Ballroom.
- **Automated:** `test_a_blocked_change_is_not_applied_by_a_later_save`

**TC-52-13 · The view still shows the saved values**
- **Traces to:** AC3 · **Type:** Happy path
- **Steps:** 1. Try to change E1's venue and start time. 2. Open E1's planning information (SCRUM-34).
- **Expected result:** It shows Aurora Ballroom and 17:00.
- **Automated:** `test_view_still_shows_the_saved_values`

**TC-52-14 · Save failure**
- **Traces to:** AC3, AC4 · **Type:** Negative (failure)
- **Preconditions:** Writes to the database fail.
- **Steps:** Change E1's description and venue.
- **Expected result:** HTTP 503 with `retryable: true`. Nothing changes.
- **Automated:** `test_save_failure_with_a_restricted_change_saves_nothing`

## AC4 — Other edits are unaffected

**TC-52-15 · Normal edits in the same save are kept**
- **Traces to:** AC4 · **Type:** Happy path · **Depends on:** Q3
- **Steps:** Change E1's description and venue in one save.
- **Expected result:** HTTP 200 with a message saying what was saved and what needs review. The description is saved; the venue is not. `requires_review` names only `venue_id`.
- **Automated:** `test_normal_edits_are_saved_alongside_a_blocked_change`

**TC-52-16 · Response shows the event as it is now**
- **Traces to:** AC3, AC4 · **Type:** Happy path
- **Steps:** As TC-52-15.
- **Expected result:** The event information in the response shows the new description and the old venue, the same as the planning view.
- **Automated:** `test_response_shows_the_saved_edit_and_the_unchanged_venue`

**TC-52-17 · Editing continues normally after a block**
- **Traces to:** AC4 · **Type:** Happy path
- **Steps:** 1. Try to change E1's venue (blocked). 2. Change the title. 3. Change the description.
- **Expected result:** Steps 2 and 3 save normally, with no `requires_review`.
- **Automated:** `test_editing_continues_normally_after_a_block`

**TC-52-18 · An invalid normal field still stops the whole save**
- **Traces to:** AC4 · **Type:** Negative · **Depends on:** B6
- **Steps:** Send a blank title, a new description and a new venue.
- **Expected result:** HTTP 422. `fields` names `title` only (the venue is not a correction). `requires_review` names `venue_id`. Nothing is saved.
- **Automated:** `test_invalid_normal_field_still_stops_the_save`

**TC-52-19 · A field that can't be changed at all still stops the whole save**
- **Traces to:** AC4 · **Type:** Negative · **Depends on:** B6
- **Steps:** Send a new status, a new description and a new venue.
- **Expected result:** HTTP 422 naming `status`. Nothing is saved.
- **Automated:** `test_non_editable_field_still_stops_the_save`

---

## Traceability matrix

| AC | Test cases |
|----|-----------|
| AC1 | 01–06 |
| AC2 | 01, 07, 08, 09, 10 |
| AC3 | 11, 12, 13, 14, 16 |
| AC4 | 05, 14, 15–19 |

| Type | Test cases |
|------|-----------|
| Happy path | 07, 08, 09, 13, 15, 16, 17 |
| Negative | 01, 02, 03, 06, 10, 11, 12, 14, 18, 19 |
| Boundary | 04, 05 |

## Open questions for the customer

| # | Question | Affects |
|---|----------|---------|
| Q1 | Are venue, start time and end time the full list of important fields? Is the title one too (see SCRUM-53, Q1)? | B1, all cases |
| Q2 | Should the normal-edit flow check that a requested venue exists and is free, or only the review process? | B3, TC-52-06 |
| Q3 | When a save mixes normal and restricted changes, should the normal ones be saved (current behaviour) or should the coordinator confirm first? | B5, TC-52-15 |
| Q4 | Should blocking a change create the change request automatically, or should the coordinator submit it? The next step assumes the SCRUM-46 endpoint will be `POST /api/events/<id>/change-requests`; confirm with the SCRUM-46 owner. | B7, B8, TC-52-08 |
